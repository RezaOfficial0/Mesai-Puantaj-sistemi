"""'Genel Bazda Giriş-Çıkış Raporu' (.xlsm) ayrıştırıcı.

Kasım 2026'dan itibaren PDKS'den gelen biçim:
  - Başlık satırı: Kart | Sicil No | Personel Adı | Soyadı | Giriş | EM | Çıkış | EM | Durumu |
                   Vardiya | Geç Gelme | Erken Çıkma | Fazla Mesai
  - Her gün için "01.11.2026 Pazar" satırı, altında o günün tüm personeli.
  - Gün sonunda "GENEL TOPLAM : N adet personel listelendi" + giriş/devamsız/izinli özet satırları.
  - Saatler datetime.time. Şirket/bölüm/hesap grubu YOK -> kart_no ile referans kişi listesinden alınır.

Çıktı, parse_puantaj ile birebir aynı şemadadır (kural motoru değişmeden çalışır).
Sadece bilinen sütunlar başlık adıyla okunur: dosyaya maaş vb. sütun eklense bile okunmaz.
(.xls hâli pandas'ta boş çıkıyor; .xlsm kullanılmalı.)
"""
import datetime as dt
import re
from pathlib import Path

import openpyxl
import pandas as pd

from parse_puantaj import split_durum

ROOT = Path(__file__).resolve().parent.parent
GENEL_FILE = ROOT / "data" / "raw" / "giriş çıkış 01.11.2026 - 15.11.2026.xlsm"

GUN_DESENI = re.compile(r"^(\d{2}\.\d{2}\.\d{4})\s+\S+$")      # "02.11.2026 Pazartesi"
LISTELENDI = re.compile(r"(\d+)\s+adet personel listelendi")
OZET_DESENI = re.compile(r"(\d+)\s+personel\s+(giriş yaptı|devamsız|izinli)")

GEREKLI_BASLIKLAR = ["Kart", "Personel Adı", "Soyadı", "Giriş", "Çıkış", "Durumu",
                     "Vardiya", "Geç Gelme", "Erken Çıkma", "Fazla Mesai"]
KISI_BILGI_SUTUNLARI = ["sirket", "departman", "bolum", "hesap_grubu", "ise_giris", "isten_cikis"]
GUNLER_SUTUNLARI = [
    "kart_no", "tarih",
    "giris_dk", "cikis_dk", "giris_manuel", "cikis_manuel",
    "giris_2_dk", "cikis_2_dk",
    "izin", "tatil", "vardiya",
    "gec_gelme_dk", "erken_cikma_dk", "fazla_mesai_dk",
    "anomali",
]
DK_SUTUNLARI = ["giris_dk", "cikis_dk", "giris_2_dk", "cikis_2_dk",
                "gec_gelme_dk", "erken_cikma_dk", "fazla_mesai_dk"]


def time_to_dk(deger):
    """datetime.time(8, 13) -> 493, None -> None."""
    if deger is None:
        return None
    if isinstance(deger, dt.datetime):
        deger = deger.time()
    if not isinstance(deger, dt.time):
        raise ValueError(f"Beklenmeyen saat değeri: {deger!r}")
    return deger.hour * 60 + deger.minute


def _sutun_indeksleri(baslik):
    baslik = [None if b is None else str(b).strip() for b in baslik]
    eksik = [b for b in GEREKLI_BASLIKLAR if b not in baslik]
    if eksik:
        raise ValueError(f"Başlık satırında eksik sütun: {eksik}")
    s = {b: baslik.index(b) for b in GEREKLI_BASLIKLAR}
    # İki 'EM' sütunu var: Giriş'ten ve Çıkış'tan hemen sonra gelenler
    for ad, ana in [("EM_giris", "Giriş"), ("EM_cikis", "Çıkış")]:
        i = s[ana] + 1
        if baslik[i] != "EM":
            raise ValueError(f"'{ana}' sütunundan sonra 'EM' bekleniyordu, '{baslik[i]}' geldi")
        s[ad] = i
    return s


def _em(deger):
    """'*' -> (True, ''), boş -> (False, ''), başka -> (False, değer) [anomali]."""
    if deger is None or str(deger).strip() == "":
        return False, ""
    metin = str(deger).strip()
    return (True, "") if metin == "*" else (False, metin)


def oku_genel(route):
    """Ham satırları okur: kisiler (kart_no, ad, soyad), gunler, gun_ozet (dosyanın kendi sayıları)."""
    ws = openpyxl.load_workbook(route, read_only=True, data_only=True).worksheets[0]
    satirlar = list(ws.iter_rows(values_only=True))

    baslik_i = next(i for i, r in enumerate(satirlar) if r and r[0] == "Kart")
    s = _sutun_indeksleri(satirlar[baslik_i])

    kayitlar, ozetler, adlar = [], [], {}
    gun, gun_ozet = None, None
    for r in satirlar[baslik_i + 1:]:
        ilk = r[0]
        if isinstance(ilk, str) and GUN_DESENI.match(ilk.strip()):
            gun = pd.to_datetime(GUN_DESENI.match(ilk.strip()).group(1), format="%d.%m.%Y")
            gun_ozet = {"tarih": gun}
            ozetler.append(gun_ozet)
            continue
        metin = " ".join(str(c) for c in r if c is not None).replace("\xa0", " ")
        if (m := LISTELENDI.search(metin)) is not None:
            gun_ozet["listelendi"] = int(m.group(1))
            continue
        if (m := OZET_DESENI.search(metin)) is not None:
            gun_ozet[m.group(2).replace(" ", "_").replace("ş", "s").replace("ı", "i")] = int(m.group(1))
            continue
        if isinstance(ilk, int):
            if gun is None:
                raise ValueError("Gün başlığından önce personel satırı geldi")
            kart_no = str(ilk).zfill(5)
            adlar.setdefault(kart_no, (str(r[s["Personel Adı"]]).strip(), str(r[s["Soyadı"]]).strip()))
            g_man, g_an = _em(r[s["EM_giris"]])
            c_man, c_an = _em(r[s["EM_cikis"]])
            izin, tatil = split_durum(r[s["Durumu"]])
            kayitlar.append({
                "kart_no": kart_no,
                "tarih": gun,
                "giris_dk": time_to_dk(r[s["Giriş"]]),
                "cikis_dk": time_to_dk(r[s["Çıkış"]]),
                "giris_manuel": g_man,
                "cikis_manuel": c_man,
                "giris_2_dk": None,           # bu raporda aynı gün ikinci çift yok
                "cikis_2_dk": None,
                "izin": izin,
                "tatil": tatil,
                "vardiya": r[s["Vardiya"]],
                "gec_gelme_dk": time_to_dk(r[s["Geç Gelme"]]),
                "erken_cikma_dk": time_to_dk(r[s["Erken Çıkma"]]),
                "fazla_mesai_dk": time_to_dk(r[s["Fazla Mesai"]]),
                "anomali": "; ".join(p for p in (f"giris:{g_an}" if g_an else "",
                                                 f"cikis:{c_an}" if c_an else "") if p) or None,
            })
            continue
        if any(c is not None for c in r):
            raise ValueError(f"Tanınmayan satır: {r}")

    gunler = pd.DataFrame(kayitlar, columns=GUNLER_SUTUNLARI)
    for c in DK_SUTUNLARI:
        gunler[c] = gunler[c].astype("Int64")
    # parse_puantaj ile birebir aynı tipler (pandas 3): tarih us, kart_no/vardiya str, izin/tatil/anomali object
    gunler["tarih"] = gunler["tarih"].astype("datetime64[us]")
    for c in ["kart_no", "vardiya"]:
        gunler[c] = pd.Series(gunler[c].tolist(), index=gunler.index, dtype="str")
    for c in ["izin", "tatil", "anomali"]:
        gunler[c] = gunler[c].astype(object)

    gun_ozet = pd.DataFrame(ozetler)
    sayim = gunler.groupby("tarih").size()
    uyusmayan = gun_ozet[gun_ozet["listelendi"].to_numpy() != sayim.reindex(gun_ozet["tarih"]).to_numpy()]
    if len(uyusmayan):
        raise ValueError(f"Gün özetindeki kişi sayısı satır sayısıyla tutmuyor: {uyusmayan.to_dict('records')}")

    kisiler = pd.DataFrame([{"kart_no": k, "ad": a, "soyad": s_} for k, (a, s_) in adlar.items()])
    return kisiler, gunler, gun_ozet


def parse_genel(route=GENEL_FILE, referans_kisiler=None):
    """parse_puantaj ile aynı (kisiler, gunler) çıktısı.

    referans_kisiler: şirket/bölüm/hesap grubu bilgisini almak için parse_puantaj'ın
    kisiler tablosu (ör. son aylık puantaj). Referansta olmayan kişiler için bu alanlar boş kalır;
    kural motorunda İDARİ sayılmazlar, istisna listesine düşmeleri gerekir.
    """
    kisiler, gunler, _ = oku_genel(route)
    if referans_kisiler is not None:
        ref = referans_kisiler.drop_duplicates("kart_no", keep="last").set_index("kart_no")
        for c in KISI_BILGI_SUTUNLARI:
            kisiler[c] = kisiler["kart_no"].map(ref[c])
    else:
        for c in KISI_BILGI_SUTUNLARI:
            kisiler[c] = None
    return kisiler, gunler


if __name__ == "__main__":
    from parse_puantaj import parse_puantaj

    ref, _ = parse_puantaj(ROOT / "data" / "raw" / "ekim yüz okuma.xls")
    kisiler, gunler = parse_genel(GENEL_FILE, ref)
    _, _, gun_ozet = oku_genel(GENEL_FILE)
    print(kisiler.shape, gunler.shape)
    print("referansta olmayan:", kisiler.loc[kisiler["hesap_grubu"].isna(), "kart_no"].tolist())
    print(gun_ozet.to_string())
