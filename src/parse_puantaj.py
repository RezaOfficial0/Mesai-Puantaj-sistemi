from pathlib import Path
import pandas as pd
import re
from io import StringIO

ROOT = Path(__file__).resolve().parent.parent
PUANTAJ_FILE = ROOT / "data" / "raw" / "puantaj.xls"
SAAT_DESENI = re.compile(r"^(\d{1,3}):(\d{2})$")
TATILLER = ["RESMİ TATİL (12:30-23:59)", "RESMİ TATİL", "HAFTA TATİLİ"]



def is_header(df) -> bool:
    return str(df.iloc[0, 0]).strip() == "Kart No:"


def read_header(df) -> dict:
    dictionary = {}
    for row in range(4):
        for col in [0, 2, 4]:
            label = df.iloc[row, col]
            value = df.iloc[row, col+1]
            label = str(label).strip().rstrip(":")

            dictionary[label] = value
    return dictionary

def pair_tables(tables) -> list:
    people = []
    i = 1
    while i < len(tables):
        if is_header(tables[i]):
            header = read_header(tables[i])
            days = tables[i + 1]
            if days.columns[0] != "Tarih":
                raise ValueError(f"{i}. tablodan sonra günlük tablo bekleniyordu")
            people.append((header, days))
            i+=2
        else:
            print(f"Beklenmeyen tablo: indeks {i}, boyut {tables[i].shape}")
            i+=1
    return people

def clean_days(days, kart_no):
    days = days.copy()

    # 5a) TOPLAM satırını ayır
    mask = days["Tarih"].astype(str).str.startswith("TOPLAM")
    toplam = days[mask].copy()
    days = days[~mask].copy()
    # 5a-2) Aynı güne ait ikinci giriş-çıkış çiftini ilk satıra taşı
    ikinci = days["Tarih"].duplicated(keep="first")
    days["giris_2"] = None
    days["cikis_2"] = None
    for idx in days.index[ikinci]:
        tarih = days.at[idx, "Tarih"]
        ilk = days.index[(days["Tarih"] == tarih) & ~ikinci][0]
        days.at[ilk, "giris_2"] = days.at[idx, "Giriş"]
        days.at[ilk, "cikis_2"] = days.at[idx, "Çıkış"]
    days = days[~ikinci].copy()


    # 5b) Tarihi çevir: "01.10.2026 Perşembe" -> 2026-10-01
    days["tarih"] = pd.to_datetime(
        days["Tarih"].astype(str).str.split().str[0],
        format="%d.%m.%Y",
    )

    # 5c) Saatleri dakikaya çevir
    saat_sutunlari = {
        "Giriş": "giris_dk",
        "Çıkış": "cikis_dk",
        "giris_2": "giris_2_dk",
        "cikis_2": "cikis_2_dk",
        "Geç Gelme": "gec_gelme_dk",
        "Erken Çıkma": "erken_cikma_dk",
        "Fazla Mesai": "fazla_mesai_dk",
    }
    for eski, yeni in saat_sutunlari.items():
        days[yeni] = days[eski].map(saat_to_dk).astype("Int64")

    # 5d) EM sütunları: "*" = elle düzeltilmiş kayıt, başka değer = anomali
    days["giris_manuel"] = days["EM"].astype(str).str.strip().eq("*")
    days["cikis_manuel"] = days["EM.1"].astype(str).str.strip().eq("*")

    def em_anomali(deger):
        """'*' ve boş normaldir. Başka bir değer (ör. '06:53') anomalidir."""
        if pd.isna(deger):
            return ""
        metin = str(deger).strip()
        return "" if metin in ("", "*") else metin

    giris_an = days["EM"].map(em_anomali)
    cikis_an = days["EM.1"].map(em_anomali)
    days["anomali"] = [
        "; ".join(p for p in (f"giris:{g}" if g else "", f"cikis:{c}" if c else "") if p) or None
        for g, c in zip(giris_an, cikis_an)
    ]


    ayrik = days["Durumu"].map(split_durum)
    days["izin"] = ayrik.str[0]
    days["tatil"] = ayrik.str[1]
    days["vardiya"] = days["Vardiya"]
    days["kart_no"] = str(kart_no).zfill(5)

    days = days[[
        "kart_no", "tarih",
        "giris_dk", "cikis_dk", "giris_manuel", "cikis_manuel",
        "giris_2_dk", "cikis_2_dk",
        "izin", "tatil", "vardiya",
        "gec_gelme_dk", "erken_cikma_dk", "fazla_mesai_dk",
        "anomali",
    ]].reset_index(drop=True)

    return days, toplam

def saat_to_dk(deger):
    """'08:21' -> 501, '68:02' -> 4082, NaN/boş -> None."""
    if pd.isna(deger):
        return None
    metin = str(deger).strip()
    eslesme = SAAT_DESENI.match(metin)
    if eslesme is None:
        return None
    saat, dakika = eslesme.groups()
    return int(saat) * 60 + int(dakika)


def split_durum(metin):
    if pd.isna(metin):
        return None, None

    metin = str(metin).strip()

    tatil = None
    for t in TATILLER:
        if t in metin:
            tatil = t
            metin = metin.replace(t, "")
            break
    metin = metin.strip()
    if metin == "":
        izin = None
    else:
        izin = metin

    return izin, tatil

def read_tables(route):
    html = Path(route).read_text(encoding="iso-8859-9")
    # Programın HTML'inde bazı satırlarda <tr> eksik: "</tr><td ..." -> "</tr><tr><td ..."
    html = re.sub(r"</tr>(\s*)<td", r"</tr><tr>\1<td", html, flags=re.IGNORECASE)
    return pd.read_html(StringIO(html))

def parse_puantaj(route):
    tables = read_tables(route)


    people = pair_tables(tables)


    kisi_listesi = []
    gun_listesi = []

    for header, days in people:
        kart_no = str(header["Kart No"]).zfill(5)


        kisi_listesi.append({
            "kart_no": kart_no,
            "ad": header["Adı"],
            "soyad": header["Soyadı"],
            "sirket": header["Şirket"],
            "departman": header["Departman"],
            "bolum": header["Bölüm"],
            "hesap_grubu": header["Hesap Grubu"],
            "ise_giris": header["Giriş Tarih"],
            "isten_cikis": header["Çıkış Tarihi"],
        })


        temiz, toplam = clean_days(days, kart_no)
        gun_listesi.append(temiz)


    kisiler = pd.DataFrame(kisi_listesi)
    gunler = pd.concat(gun_listesi, ignore_index=True)

    return kisiler, gunler


if __name__ == "__main__":
    kisiler, gunler = parse_puantaj(PUANTAJ_FILE)
    print(kisiler.shape)
    print(gunler.shape)
    print(kisiler["sirket"].value_counts())
    print(kisiler.head(3))
