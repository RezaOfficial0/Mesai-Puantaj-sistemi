"""Kural motoru v2 (v1 + Kural 6 resmi tatil).

Kurallar, üç aylık puantaj ile bordro karşılaştırılarak tek tek eklendi.
Her kuralın yanında Ağustos/Eylül'de ne kadar iyileştirdiği yazıyor.
Bilinmeyen değerler VARSAYIM olarak işaretli; babadan/muhasebeden teyit edilecek.
"""
import re

import numpy as np
import pandas as pd

from tatiller import kesisim_dk

# --- Ayarlar (ileride config/kurallar.xlsx'e taşınacak) ------------------------
YUVARLAMA_DK = 30            # günlük fazla mesai en yakın yarım saate yuvarlanır (VARSAYIM: yukarı/aşağı eşik 15 dk)
DEVAMSIZ_KESINTI_DK = 450    # devamsız gün başına 7,5 saat (şirketin yazılı kuralı)
AY_GUNU = 30                 # bordroda tam ay
ERKEN_GELME_MAX_DK = 180     # vardiya başından en fazla bu kadar önce gelen "erken gelmiş" sayılır
VARDIYA_DESENI = re.compile(r"(\d{2})-(\d{2})")


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


def _vardiya_baslangic_dk(vardiya):
    """'HAFTA İÇİ 19-07' -> 1140. Saat yazmayan vardiya (ör. 'İDARİ HAFTA İÇİ') -> None."""
    if pd.isna(vardiya):
        return None
    m = VARDIYA_DESENI.search(str(vardiya))
    return int(m.group(1)) * 60 if m else None


def _calisma_araliklari(satir):
    """Bir günün çalışma aralıkları [(bas, bit), ...] (Timestamp).

    Erken gelme sayılmaz: giriş, vardiya başlangıcından önceyse vardiya başlangıcı alınır.
    Çıkış girişten küçük/eşitse ertesi güne geçmiştir (gece vardiyası).
    Giriş ya da çıkışı eksik olan çift atlanır (istisna listesine ayrıca düşecek).
    """
    gun = satir["tarih"]
    araliklar = []
    for g_sut, c_sut, kirp in [("giris_dk", "cikis_dk", True), ("giris_2_dk", "cikis_2_dk", False)]:
        giris, cikis = satir[g_sut], satir[c_sut]
        if pd.isna(giris) or pd.isna(cikis):
            continue
        giris, cikis = int(giris), int(cikis)
        bas_dk = giris
        vb = _vardiya_baslangic_dk(satir["vardiya"]) if kirp else None
        if vb is not None and 0 < vb - giris <= ERKEN_GELME_MAX_DK:
            bas_dk = vb
        bit_dk = cikis if cikis > giris else cikis + 24 * 60
        araliklar.append((gun + pd.Timedelta(minutes=bas_dk), gun + pd.Timedelta(minutes=bit_dk)))
    return araliklar


def tatil_kesisim_dk(g, tatiller):
    """Her gün için çalışmanın resmi tatil aralıklarına düşen ham (yuvarlanmamış) dakikası."""
    if len(g) == 0:
        return pd.Series(dtype="int64")
    alt, ust = g["tarih"].min() - pd.Timedelta(days=1), g["tarih"].max() + pd.Timedelta(days=2)
    t = tatiller[(tatiller["bitis"] > alt) & (tatiller["baslangic"] < ust)]
    if len(t) == 0:
        return pd.Series(0, index=g.index)
    return g.apply(
        lambda s: sum(kesisim_dk(b, e, t) for b, e in _calisma_araliklari(s)), axis=1
    ).astype("int64")


def gunluk_mesai_tatilli(g, tatiller):
    """Kural 1-4 + Kural 6: fazla mesai (fm_dk) ve resmi tatil mesaisi (ht_dk) ayrı ayrı.

    Kural 6 : resmi tatil aralığına düşen tüm çalışma (normal mesai dahil) tatil mesaisidir,
              en yakın 30 dk'ya yuvarlanır. Ekim: bordro 'hafta tatili' sütunu 228 sa = bizim 228 sa.
              Kişinin günü HAFTA TATİLİ ise yazılmaz (Ağustos 30: Pazar'a denk gelen
              Zafer Bayramı'nda çalışana bordroda ayrı ödeme yok). İDARİ = 0.
    Kural 6b: tatille kesişen günün fazla mesaisi fm'ye yazılmaz (tatil mesaisinin içinde).
              VARSAYIM: gece vardiyası tatil bitiminden sonraya taşarsa tatil dışındaki
              fazla mesai de silinir; veride örneği yok, müdüre sorulacak.
    """
    fm = gunluk_mesai(g)
    kesisim = tatil_kesisim_dk(g, tatiller)

    hafta_tatili = g["tatil"].fillna("").str.contains("HAFTA")
    idari = g["hesap_grubu"].fillna("").str.contains("İDARİ")
    ht = _yuvarla(kesisim).where(~hafta_tatili & ~idari, 0)

    fm = fm.where(~((kesisim > 0) & ~hafta_tatili), 0)
    return pd.DataFrame({"fm_dk": fm, "ht_dk": ht}, index=g.index)


def aylik_son_islem(tablo, g, devamsiz_modu="gun_30"):
    """Kişi bazında devamsızlık kesintisi, alt sınır ve aylık yuvarlama (sadece fazla mesai, fm).

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

    dk = tablo["bizim_fm_dk"].astype(float).to_numpy() - kesinti
    dk = np.clip(dk, 0, None)                         # mesai eksiye düşmez
    return pd.Series(_yuvarla(dk).astype(int), index=tablo.index)


if __name__ == "__main__":
    from parse_puantaj import parse_puantaj, ROOT
    from parse_bordro import parse_bordro
    from eslestir import manuel_oku
    from karsilastir import karsilastir, ozet, ham_puantaj, excel_yaz, AYLAR
    from tatiller import tatil_oku

    manuel = manuel_oku(ROOT / "config" / "eslestirme.csv")
    tatiller = tatil_oku()
    gun_30 = lambda t, g: aylik_son_islem(t, g, "gun_30")
    adimlar = [
        ("0 ham puantaj", ham_puantaj, None),
        ("1-4 günlük kurallar", gunluk_mesai, lambda t, g: aylik_son_islem(t, g, "kapali")),
        ("5 devamsız (her zaman)", gunluk_mesai, lambda t, g: aylik_son_islem(t, g, "her_zaman")),
        ("5 devamsız (gün=30 ise)", gunluk_mesai, gun_30),
        ("6 resmi tatil", lambda g: gunluk_mesai_tatilli(g, tatiller), gun_30),
    ]
    for ay, p_dosya, b_dosya in AYLAR:
        kisiler, gunler = parse_puantaj(ROOT / "data" / "raw" / p_dosya)
        bordro, _ = parse_bordro(ROOT / "data" / "raw" / b_dosya)
        print(f"== {ay}")
        for ad, kural, son in adimlar:
            t = karsilastir(kisiler, gunler, bordro, manuel, kural=kural, son_islem=son)
            o = ozet(t)
            print(f"   {ad:26s} tam {o['tam']:2d}/{o['kisi']} (fm {o['tam_fm']:2d}, ht {o['tam_ht']:2d})"
                  f"  ±30dk {o['yakin']:2d}  toplam fark {o['toplam_fark_saat']:+7.1f} sa  mutlak {o['mutlak_fark_saat']:6.1f} sa")
        print(f"   {'':26s} ht: bizim {t['bizim_ht_dk'].sum() / 60:.1f} sa, bordro {t['ht_dk'].sum() / 60:.1f} sa")
        excel_yaz(t, ROOT / "cikti" / f"karsilastirma_{ay}_kural_v2.xlsx")
