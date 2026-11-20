"""İlk ön tablo (demo): dönem için kişi bazında hesaplanan mesai + istisna listesi -> Excel.

Bordro olmadan çalışır (gelecek dönemler için). Bu yüzden:
  - Devamsızlık kesintisi YAPILMAZ, olası kesinti gösterilir ve 'Devamsızlık kararı' istisnası açılır
    (bordro gün = 30 ise kesiliyordu; gün bilgisi henüz yok, karar muhasebede/müdürde).
  - Eksi bakiye 0'a çekilmeden önce istisna olarak listelenir.
Ham veri değiştirilmez; her sayı Günlük Detay sayfasından geri izlenebilir.
"""
import re
from pathlib import Path

import pandas as pd

from rules import (DEVAMSIZ_KESINTI_DK, VARDIYA_DESENI, _yuvarla, calisma_dk,
                   gunluk_mesai_tatilli)

ROOT = Path(__file__).resolve().parent.parent
UZUN_GUN_DK = 12 * 60
IDARI_HATALI_FM_DK = 12 * 60 + 30
GUN_ADLARI = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]

ISTISNA_TURLERI = {           # kod -> (başlık, önerilen işlem)
    "HATALI_ESLESME": ("Ters giriş-çıkış (12:30 hatası)", "Kontrol: PDKS'de giriş-çıkış eşleşmesi düzeltilmeli"),
    "EKSIK_CIKIS": ("Eksik çıkış", "Müdüre sor: çıkış saati"),
    "EKSIK_GIRIS": ("Eksik giriş", "Müdüre sor: giriş saati"),
    "UZUN_GUN": ("12 saati aşan gün", "Kontrol: gerçekten bu kadar çalıştı mı"),
    "TATILDE_CALISMA": ("Tatilde çalışma", "Müdüre sor: ödenecek mi"),
    "EKSI_BAKIYE": ("Eksi bakiye", "Müdüre sor: geç gelme/erken çıkma kesintisi mesaiden fazla"),
    "DEVAMSIZLIK_KARARI": ("Devamsızlık kararı", "Muhasebeye sor: günden mi mesaiden mi kesilecek"),
    "KISI_BILGISI_YOK": ("Kişi bilgisi yok", "Personel listesine ekle (hesap grubu bilinmiyor)"),
}


def _hm(dk):
    if pd.isna(dk):
        return None
    dk = int(dk)
    isaret = "-" if dk < 0 else ""
    return f"{isaret}{abs(dk) // 60:02d}:{abs(dk) % 60:02d}"


def _hm_yok(dk):
    """Açıklama metinleri için: eksik saat 'yok' yazılır."""
    return _hm(dk) or "yok"


def _saat(dk):
    return round(float(dk) / 60, 2)


def _gece_vardiyasi(vardiya):
    """'HAFTA İÇİ 19-07' -> True (gün aşar). İDARİ / saat yazmayan -> False."""
    if pd.isna(vardiya):
        return False
    m = VARDIYA_DESENI.search(str(vardiya))
    return bool(m) and int(m.group(2)) < int(m.group(1))


def hatali_eslesme(g):
    """Gün aşmayan vardiyada çıkış girişten önce/eşit: akşam çıkışı 'giriş', ertesi sabahın
    girişi 'çıkış' olarak eşleşmiş (İDARİ'de PDKS bu durumda 12:30 fazla mesai yazıyor)."""
    gece = g["vardiya"].map(_gece_vardiyasi)
    ters = g["giris_dk"].notna() & g["cikis_dk"].notna() & (g["cikis_dk"] <= g["giris_dk"])
    return (ters & ~gece).fillna(False).astype(bool)


def gun_tablosu(kisiler, gunler, tatiller):
    """Her kişi-gün için hesaplanan değerler + o güne ait istisna kodları."""
    g = gunler.merge(kisiler[["kart_no", "ad", "soyad", "hesap_grubu"]], on="kart_no", how="left")
    g["ad_soyad"] = g["ad"].fillna("") + " " + g["soyad"].fillna("")
    sonuc = gunluk_mesai_tatilli(g, tatiller)
    g["bizim_fm_dk"] = sonuc["fm_dk"].astype("int64")
    g["bizim_ht_dk"] = sonuc["ht_dk"].astype("int64")
    g["calisma_dk"] = calisma_dk(g)

    basti = g["giris_dk"].notna() | g["cikis_dk"].notna()
    g["kart_basti"] = basti
    bayrak = pd.DataFrame(index=g.index)
    bayrak["HATALI_ESLESME"] = hatali_eslesme(g)
    bayrak["EKSIK_CIKIS"] = g["giris_dk"].notna() & g["cikis_dk"].isna()
    bayrak["EKSIK_GIRIS"] = g["giris_dk"].isna() & g["cikis_dk"].notna()
    # Kural 1 ile aynı tolerans: en yakın 30 dk'ya yuvarlanınca 12 saati aşan (07:00-19:10 sayılmaz)
    bayrak["UZUN_GUN"] = (_yuvarla(g["calisma_dk"]) > UZUN_GUN_DK) & ~bayrak["HATALI_ESLESME"]
    bayrak["TATILDE_CALISMA"] = basti & g["tatil"].notna()
    g["istisna"] = bayrak.apply(lambda r: ", ".join(k for k, v in r.items() if v), axis=1).replace("", None)
    return g, bayrak


def _gun_aciklama(kod, s):
    fm = 0 if pd.isna(s["fazla_mesai_dk"]) else int(s["fazla_mesai_dk"])
    if kod == "HATALI_ESLESME":
        etki = -_saat(fm - s["bizim_fm_dk"])
        if "İDARİ" in str(s["hesap_grubu"]):
            return (f"Giriş {_hm(s['giris_dk'])}, çıkış {_hm(s['cikis_dk'])} (ters): akşam çıkışı ile ertesi sabah "
                    f"girişi eşleşmiş. PDKS fazla mesai {_hm(fm)}; biz {_hm(s['bizim_fm_dk'])} yazdık."), etki
        return (f"Vardiya {s['vardiya']} gün aşmıyor ama çıkış ertesi gün ({_hm(s['giris_dk'])}-{_hm(s['cikis_dk'])}, "
                f"{_hm(s['calisma_dk'])} çalışma). Gece mi kaldı, eşleşme mi hatalı? "
                f"PDKS fazla mesai {_hm(fm)}; biz {_hm(s['bizim_fm_dk'])} yazdık."), etki
    if kod == "EKSIK_CIKIS":
        return f"Giriş {_hm(s['giris_dk'])}, çıkış yok. Mesai hesaplanamadı (0).", None
    if kod == "EKSIK_GIRIS":
        return f"Giriş yok, çıkış {_hm(s['cikis_dk'])}. Mesai hesaplanamadı (0).", None
    if kod == "UZUN_GUN":
        return (f"Vardiya başından çıkışa {_hm(s['calisma_dk'])} çalışma "
                f"({_hm_yok(s['giris_dk'])}-{_hm_yok(s['cikis_dk'])}, {s['vardiya']})."), None
    if kod == "TATILDE_CALISMA":
        if "RESMİ" in str(s["tatil"]):
            return f"{s['tatil']}: {_hm(s['bizim_ht_dk'])} tatil mesaisi yazıldı.", None
        ne_zaman = f"{s['tatil']} günü {_hm_yok(s['giris_dk'])}-{_hm_yok(s['cikis_dk'])} kart basmış, PDKS fazla mesai {_hm(fm)}."
        if "İDARİ" in str(s["hesap_grubu"]):
            return f"{ne_zaman} İDARİ: fazla mesai yazılmaz (Kural 4).", -_saat(fm)
        return f"{ne_zaman} Bordroda ödenmiyordu (Kural 2), yazılmadı. Yazılı kural: pazar x2.", -_saat(fm)
    raise ValueError(kod)


def kisi_ozeti(kisiler, g):
    grup = g.groupby("kart_no")
    oz = pd.DataFrame({
        "calisilan_gun": grup["kart_basti"].sum(),
        "devamsiz_gun": grup["izin"].agg(lambda s: int(s.eq("Devamsız").sum())),
        "izinli_gun": grup["izin"].agg(lambda s: int((s.notna() & s.ne("Devamsız")).sum())),
        "elle_duzeltme": grup.apply(lambda d: int((d["giris_manuel"] | d["cikis_manuel"]).sum()),
                                    include_groups=False),
        "puantaj_fm_dk": grup["fazla_mesai_dk"].agg(lambda s: int(s.fillna(0).sum())),
        "bizim_fm_dk": grup["bizim_fm_dk"].sum(),
        "bizim_ht_dk": grup["bizim_ht_dk"].sum(),
    })
    oz = kisiler.merge(oz, left_on="kart_no", right_index=True, how="inner")
    oz["ad_soyad"] = oz["ad"] + " " + oz["soyad"]
    idari = oz["hesap_grubu"].fillna("").str.contains("İDARİ")
    oz["olasi_kesinti_dk"] = (oz["devamsiz_gun"] * DEVAMSIZ_KESINTI_DK).where(~idari, 0)
    oz["fm_kesintisiz_dk"] = _yuvarla(oz["bizim_fm_dk"].clip(lower=0))
    oz["fm_kesintili_dk"] = _yuvarla((oz["bizim_fm_dk"] - oz["olasi_kesinti_dk"]).clip(lower=0))
    return oz.sort_values(["hesap_grubu", "kart_no"]).reset_index(drop=True)


def istisnalar(g, bayrak, oz):
    satirlar = []
    for kod in ["HATALI_ESLESME", "EKSIK_CIKIS", "EKSIK_GIRIS", "UZUN_GUN", "TATILDE_CALISMA"]:
        for i in g.index[bayrak[kod]]:
            s = g.loc[i]
            aciklama, etki = _gun_aciklama(kod, s)
            satirlar.append({"kart_no": s["kart_no"], "ad_soyad": s["ad_soyad"], "hesap_grubu": s["hesap_grubu"],
                             "tarih": s["tarih"], "kod": kod, "aciklama": aciklama, "etki_saat": etki})
    for _, s in oz.iterrows():
        kisi = {"kart_no": s["kart_no"], "ad_soyad": s["ad_soyad"], "hesap_grubu": s["hesap_grubu"], "tarih": pd.NaT}
        uretim = "İDARİ" not in str(s["hesap_grubu"])
        if pd.isna(s["hesap_grubu"]):
            satirlar.append({**kisi, "kod": "KISI_BILGISI_YOK",
                             "aciklama": "Referans listede yok; İDARİ/ÜRETİM bilinmiyor, ÜRETİM gibi hesaplandı.",
                             "etki_saat": None})
        if uretim and s["bizim_fm_dk"] < 0:
            satirlar.append({**kisi, "kod": "EKSI_BAKIYE",
                             "aciklama": f"Dönem toplamı {_hm(s['bizim_fm_dk'])}; 0'a çekildi.",
                             "etki_saat": -_saat(s["bizim_fm_dk"])})
        if uretim and s["devamsiz_gun"] > 0:
            satirlar.append({**kisi, "kod": "DEVAMSIZLIK_KARARI",
                             "aciklama": (f"{s['devamsiz_gun']} gün devamsız. Mesaiden kesilirse "
                                          f"-{_hm(s['olasi_kesinti_dk'])} (fm {_hm(s['fm_kesintisiz_dk'])} -> "
                                          f"{_hm(s['fm_kesintili_dk'])}). Şu an KESİLMEDİ."),
                             "etki_saat": -_saat(s["fm_kesintisiz_dk"] - s["fm_kesintili_dk"])})
    ist = pd.DataFrame(satirlar, columns=["kart_no", "ad_soyad", "hesap_grubu", "tarih", "kod", "aciklama", "etki_saat"])
    ist["tur"] = ist["kod"].map(lambda k: ISTISNA_TURLERI[k][0])
    ist["onerilen"] = ist["kod"].map(lambda k: ISTISNA_TURLERI[k][1])
    # İDARİ'de eksik kart / tatil çalışması mesaiyi değiştirmez: sadece bilgi
    bilgi = ist["hesap_grubu"].fillna("").str.contains("İDARİ") & ist["kod"].isin(
        ["EKSIK_CIKIS", "EKSIK_GIRIS", "TATILDE_CALISMA"])
    ist.loc[bilgi, "onerilen"] = "Bilgi: İDARİ, mesaiye etkisi yok"
    ist["mudur_karari"] = None
    sira = {k: i for i, k in enumerate(ISTISNA_TURLERI)}
    ist = ist.sort_values(["kod", "kart_no", "tarih"], key=lambda s: s.map(sira) if s.name == "kod" else s)
    return ist.reset_index(drop=True)


def on_tablo(kisiler, gunler, tatiller):
    g, bayrak = gun_tablosu(kisiler, gunler, tatiller)
    oz = kisi_ozeti(kisiler, g)
    ist = istisnalar(g, bayrak, oz)
    sayim = ist.groupby("kart_no").size()
    karar = ist[~ist["onerilen"].str.startswith("Bilgi")].groupby("kart_no").size()
    oz["istisna_sayisi"] = oz["kart_no"].map(sayim).fillna(0).astype(int)
    oz["karar_bekleyen"] = oz["kart_no"].map(karar).fillna(0).astype(int)
    oz["durum"] = oz["karar_bekleyen"].map(lambda n: "TAMAM" if n == 0 else "KONTROL")
    return oz, ist, g


def _kurallar_sayfasi(kaynak, g):
    return pd.DataFrame([
        ("Kaynak", f"{Path(kaynak).name}  ({g['tarih'].min():%d.%m.%Y} - {g['tarih'].max():%d.%m.%Y}, "
                   f"{g['kart_no'].nunique()} kişi, {len(g)} kişi-gün)"),
        ("1 Yuvarlama", "Günlük fazla mesai en yakın 30 dk'ya (15 dk altı 0)."),
        ("2 Hafta tatili", "Hafta tatilinde çalışma fazla mesaiye yazılmaz (istisna listesine düşer)."),
        ("3 Geç gelme / erken çıkma", "Fazla mesaiden düşülür."),
        ("4 İDARİ", "İDARİ personele fazla mesai yazılmaz."),
        ("5 Devamsızlık", "Bu tabloda KESİLMEDİ. Olası kesinti (gün x 7,5 sa) ayrı sütunda; karar bekliyor."),
        ("6 Resmi tatil", "Tatil aralığındaki tüm çalışma tatil mesaisi (ht); o günün fazla mesaisi fm'ye yazılmaz."),
        ("Alt sınır", "Dönem fazla mesaisi eksiye düşmez (0'a çekilir, istisna listesine düşer)."),
        ("12 saati aşan gün", "Vardiya başından (erken gelme sayılmaz) çıkışa kadar, en yakın 30 dk'ya yuvarlanınca 12 saatten fazla."),
        ("Ters giriş-çıkış", "Gün aşmayan vardiyada çıkış girişten önce. İDARİ'de akşam çıkışı + ertesi sabah girişi "
                             "eşleşmiş (PDKS 12:30 yazar, biz 0). Üretimde gece kalma da olabilir: PDKS değeri yazılır, kontrol edilir."),
        ("Not", "Saatler ondalık (4,5 = 4 sa 30 dk). Kesin hesap değildir; müdür onayından sonra kesinleşir."),
    ], columns=["kural", "aciklama"])


def excel_yaz(oz, ist, g, kaynak, yol):
    ozet = oz.copy()
    for c in ["puantaj_fm_dk", "bizim_fm_dk", "fm_kesintisiz_dk", "olasi_kesinti_dk", "fm_kesintili_dk", "bizim_ht_dk"]:
        ozet[c.replace("_dk", "_saat")] = ozet[c].map(_saat)
    ozet = ozet[["kart_no", "ad_soyad", "sirket", "bolum", "hesap_grubu",
                 "calisilan_gun", "devamsiz_gun", "izinli_gun", "elle_duzeltme",
                 "puantaj_fm_saat", "bizim_fm_saat", "fm_kesintisiz_saat", "olasi_kesinti_saat",
                 "fm_kesintili_saat", "bizim_ht_saat", "istisna_sayisi", "karar_bekleyen", "durum"]]

    istisna = ist[["kart_no", "ad_soyad", "hesap_grubu", "tarih", "tur", "aciklama",
                   "etki_saat", "onerilen", "mudur_karari"]].copy()
    istisna["tarih"] = istisna["tarih"].dt.date

    detay = pd.DataFrame({
        "kart_no": g["kart_no"], "ad_soyad": g["ad_soyad"], "hesap_grubu": g["hesap_grubu"],
        "tarih": g["tarih"].dt.date, "gun": g["tarih"].dt.day_of_week.map(lambda i: GUN_ADLARI[i]),
        "vardiya": g["vardiya"], "giris": g["giris_dk"].map(_hm), "cikis": g["cikis_dk"].map(_hm),
        "elle": (g["giris_manuel"] | g["cikis_manuel"]).map({True: "*", False: ""}),
        "izin": g["izin"], "tatil": g["tatil"],
        "gec_gelme": g["gec_gelme_dk"].map(_hm), "erken_cikma": g["erken_cikma_dk"].map(_hm),
        "puantaj_fm": g["fazla_mesai_dk"].map(_hm), "calisma": g["calisma_dk"].where(g["calisma_dk"] > 0).map(_hm),
        "bizim_fm_saat": g["bizim_fm_dk"].map(_saat), "bizim_ht_saat": g["bizim_ht_dk"].map(_saat),
        "istisna": g["istisna"],
    }).sort_values(["kart_no", "tarih"])

    sayfalar = {"Kişi Özeti": ozet, "İstisnalar": istisna, "Günlük Detay": detay,
                "Kurallar": _kurallar_sayfasi(kaynak, g)}
    with pd.ExcelWriter(yol, engine="openpyxl") as yazici:
        for ad, df in sayfalar.items():
            df.to_excel(yazici, sheet_name=ad, index=False)
            ws = yazici.sheets[ad]
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for i, sutun in enumerate(df.columns, start=1):
                uzunluk = max([len(str(sutun))] + [len(str(v)) for v in df[sutun].head(500)])
                ws.column_dimensions[ws.cell(1, i).column_letter].width = min(uzunluk + 2, 70)


if __name__ == "__main__":
    from parse_genel import parse_genel, GENEL_FILE
    from parse_puantaj import parse_puantaj
    from tatiller import tatil_oku

    referans, _ = parse_puantaj(ROOT / "data" / "raw" / "ekim yüz okuma.xls")
    kisiler, gunler = parse_genel(GENEL_FILE, referans)
    oz, ist, g = on_tablo(kisiler, gunler, tatil_oku())

    yol = ROOT / "cikti" / "on_tablo_kasim_01_15.xlsx"
    excel_yaz(oz, ist, g, GENEL_FILE, yol)

    uretim = oz[~oz["hesap_grubu"].fillna("").str.contains("İDARİ")]
    print(f"{len(oz)} kişi ({len(uretim)} üretim), {len(ist)} istisna -> {yol.relative_to(ROOT)}")
    print(f"ÜRETİM fm: puantaj {uretim['puantaj_fm_dk'].sum() / 60:.1f} sa | bizim (kesintisiz) "
          f"{uretim['fm_kesintisiz_dk'].sum() / 60:.1f} sa | devamsızlık kesilirse {uretim['fm_kesintili_dk'].sum() / 60:.1f} sa")
    print(ist.assign(bilgi=ist["onerilen"].str.startswith("Bilgi"))
          .groupby("tur", sort=False).agg(adet=("kod", "size"), kisi=("kart_no", "nunique"), bilgi=("bilgi", "sum"))
          .to_string())
    print("durum:", oz["durum"].value_counts().to_dict())
