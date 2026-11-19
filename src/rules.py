"""Kural motoru v1.

Kurallar, üç aylık puantaj ile bordro karşılaştırılarak tek tek eklendi.
Her kuralın yanında Ağustos/Eylül'de ne kadar iyileştirdiği yazıyor.
Bilinmeyen değerler VARSAYIM olarak işaretli; babadan/muhasebeden teyit edilecek.
"""
import numpy as np
import pandas as pd

# --- Ayarlar (ileride config/kurallar.xlsx'e taşınacak) ------------------------
YUVARLAMA_DK = 30            # günlük fazla mesai en yakın yarım saate yuvarlanır (VARSAYIM: yukarı/aşağı eşik 15 dk)
DEVAMSIZ_KESINTI_DK = 450    # devamsız gün başına 7,5 saat (şirketin yazılı kuralı)
AY_GUNU = 30                 # bordroda tam ay


def _yuvarla(seri, adim=YUVARLAMA_DK):
    """En yakın 'adim' dakikaya yuvarlar. 14 dk -> 0, 15 dk -> 30, 44 dk -> 30, 45 dk -> 60."""
    return ((seri + adim // 2) // adim) * adim


def gunluk_mesai(g):
    """Her gün için fazla mesai dakikası (kesintiler düşülmüş, yuvarlanmış).

    g: gunler tablosu + 'hesap_grubu' sütunu.
    """
    # Kural 1: puantajın günlük fazla mesaisi en yakın yarım saate yuvarlanır
    #          (Ağustos: tam eşleşen 4 -> 32 kişi)
    dk = _yuvarla(g["fazla_mesai_dk"].fillna(0))

    # Kural 2: hafta tatilinde yapılan çalışma normal fazla mesaiye girmez
    #          (bordroda ayrı ödeniyor ya da hiç ödenmiyor; Ekim'de 'hafta tatili' sütunu var)
    dk = dk.where(~g["tatil"].fillna("").str.contains("HAFTA"), 0)

    # Kural 3: erken çıkma ve geç gelme dakikaları fazla mesaiden düşülür
    #          (Ağustos: 34 -> 41 kişi)
    dk = dk - g["erken_cikma_dk"].fillna(0) - g["gec_gelme_dk"].fillna(0)

    # Kural 4: İDARİ personele fazla mesai yazılmaz (sözleşme: haftalık 45 saat)
    dk = dk.where(~g["hesap_grubu"].fillna("").str.contains("İDARİ"), 0)
    return dk


def aylik_son_islem(tablo, g, devamsiz_modu="gun_30"):
    """Kişi bazında devamsızlık kesintisi, alt sınır ve aylık yuvarlama.

    devamsiz_modu:
      "kapali"    : devamsızlık kesintisi yapılmaz (sadece ölçüm için)
      "her_zaman" : her devamsız gün için 7,5 saat kesilir (yazılı kural)
      "gun_30"    : sadece bordroda gün = 30 ise kesilir. Gün < 30 ise devamsızlık
                    zaten günden düşülmüş demektir, mesaiden ayrıca kesilmez.
                    (Veriyle en iyi uyan davranış. Ama bu karar şu an muhasebede veriliyor:
                     sistemde 'müdüre/muhasebeye sor' durumu olmalı.)
    """
    devamsiz = (
        g[g["izin"].eq("Devamsız")]
        .groupby("kart_no").size()
        .reindex(tablo["kart_no"]).fillna(0).to_numpy()
    )
    if devamsiz_modu == "kapali":
        kesinti = 0
    elif devamsiz_modu == "her_zaman":
        kesinti = devamsiz * DEVAMSIZ_KESINTI_DK
    elif devamsiz_modu == "gun_30":
        kesinti = np.where(tablo["gun"].to_numpy() >= AY_GUNU, devamsiz * DEVAMSIZ_KESINTI_DK, 0)
    else:
        raise ValueError(devamsiz_modu)

    dk = tablo["bizim_dk"].astype(float).to_numpy() - kesinti
    dk = np.clip(dk, 0, None)                         # mesai eksiye düşmez
    return pd.Series(_yuvarla(dk).astype(int), index=tablo.index)


if __name__ == "__main__":
    from parse_puantaj import parse_puantaj, ROOT
    from parse_bordro import parse_bordro
    from eslestir import manuel_oku
    from karsilastir import karsilastir, ozet, ham_puantaj, excel_yaz, AYLAR

    manuel = manuel_oku(ROOT / "config" / "eslestirme.csv")
    adimlar = [
        ("0 ham puantaj", ham_puantaj, None),
        ("1-4 günlük kurallar", gunluk_mesai, lambda t, g: aylik_son_islem(t, g, "kapali")),
        ("5 devamsız (her zaman)", gunluk_mesai, lambda t, g: aylik_son_islem(t, g, "her_zaman")),
        ("5 devamsız (gün=30 ise)", gunluk_mesai, lambda t, g: aylik_son_islem(t, g, "gun_30")),
    ]
    for ay, p_dosya, b_dosya in AYLAR:
        kisiler, gunler = parse_puantaj(ROOT / "data" / "raw" / p_dosya)
        bordro, _ = parse_bordro(ROOT / "data" / "raw" / b_dosya)
        print(f"== {ay}")
        for ad, kural, son in adimlar:
            t = karsilastir(kisiler, gunler, bordro, manuel, kural=kural, son_islem=son)
            o = ozet(t)
            print(f"   {ad:26s} tam {o['tam']:2d}/{o['kisi']}  ±30dk {o['yakin']:2d}  toplam fark {o['toplam_fark_saat']:+7.1f} sa  mutlak {o['mutlak_fark_saat']:6.1f} sa")
        excel_yaz(t, ROOT / "cikti" / f"karsilastirma_{ay}_kural_v1.xlsx")
