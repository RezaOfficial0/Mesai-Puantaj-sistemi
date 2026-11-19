"""Kişi bazında 'bizim hesap' ile bordroyu karşılaştırır.

Kural motoru (Adım 2c) her gün için bir fazla mesai dakikası üretecek.
Bu dosya o sonucu bordroyla yan yana koyar ve ne kadar tuttuğunu ölçer.
"""
import pandas as pd

from eslestir import eslestir, norm_ad

TOLERANS_DK = 30          # "yakın" saymak için kabul edilen fark


def ham_puantaj(gunler):
    """Başlangıç (baseline) kuralı: puantajın kendi fazla mesaisini olduğu gibi al."""
    return gunler["fazla_mesai_dk"].fillna(0)


def karsilastir(kisiler, gunler, bordro, manuel=None, kural=ham_puantaj):
    # 1) Kişi eşleştirme
    eslesme, _, _ = eslestir(kisiler, bordro, manuel)

    # 2) Bizim hesap: kuralı her güne uygula, kişi bazında topla
    g = gunler.copy()
    g["bizim_dk"] = kural(g).astype("Int64")
    g["puantaj_dk"] = g["fazla_mesai_dk"].fillna(0)
    bizim = g.groupby("kart_no")[["puantaj_dk", "bizim_dk"]].sum()

    # 3) Bordro: aynı ad birden fazla satırdaysa topla
    b = bordro.copy()
    b["anahtar"] = b["ad_soyad"].map(norm_ad)
    b = b.groupby("anahtar")[["gun", "fm_dk", "ht_dk"]].sum()
    b["bordro_dk"] = b["fm_dk"] + b["ht_dk"]

    # 4) Hepsini kart_no üzerinde birleştir
    tablo = (
        eslesme
        .merge(kisiler[["kart_no", "sirket", "bolum", "hesap_grubu"]], on="kart_no")
        .merge(bizim, left_on="kart_no", right_index=True)
        .merge(b, left_on="anahtar", right_index=True)
    )
    tablo["fark_dk"] = tablo["bizim_dk"] - tablo["bordro_dk"]
    tablo["durum"] = "FARKLI"
    tablo.loc[tablo["fark_dk"].abs() <= TOLERANS_DK, "durum"] = "YAKIN"
    tablo.loc[tablo["fark_dk"] == 0, "durum"] = "TAM"
    return tablo.sort_values("fark_dk", key=abs, ascending=False).reset_index(drop=True)


def ozet(tablo, grup="ÜRETİM"):
    """Bir kuralın ne kadar iyi olduğunu tek satırda verir."""
    t = tablo[tablo["hesap_grubu"].str.contains(grup)]
    return {
        "kisi": len(t),
        "tam": int((t["durum"] == "TAM").sum()),
        "yakin": int((t["durum"] != "FARKLI").sum()),
        "toplam_fark_saat": round(float(t["fark_dk"].sum()) / 60, 1),
        "mutlak_fark_saat": round(float(t["fark_dk"].abs().sum()) / 60, 1),
    }


def excel_yaz(tablo, yol):
    cikti = tablo.copy()
    for c in ["puantaj_dk", "bizim_dk", "bordro_dk", "fm_dk", "ht_dk", "fark_dk"]:
        cikti[c.replace("_dk", "_saat")] = (cikti[c] / 60).round(2)
    sutunlar = ["kart_no", "anahtar", "bordro_adi", "sirket", "bolum", "hesap_grubu", "gun",
                "puantaj_saat", "bizim_saat", "fm_saat", "ht_saat", "bordro_saat", "fark_saat", "durum"]
    cikti[sutunlar].to_excel(yol, index=False)


AYLAR = [
    ("ağustos", "ağustos yüz okuma.xls", "bordrolama Ağustos.xls"),
    ("eylül", "eylül yüz okuma.xls", "Bordrolama eylül.xls"),
    ("ekim", "ekim yüz okuma.xls", "Bordrolama ekim.xls"),
]


if __name__ == "__main__":
    from parse_puantaj import parse_puantaj, ROOT
    from parse_bordro import parse_bordro
    from eslestir import manuel_oku

    manuel = manuel_oku(ROOT / "config" / "eslestirme.csv")
    (ROOT / "cikti").mkdir(exist_ok=True)

    for ay, p_dosya, b_dosya in AYLAR:
        kisiler, gunler = parse_puantaj(ROOT / "data" / "raw" / p_dosya)
        bordro, _ = parse_bordro(ROOT / "data" / "raw" / b_dosya)

        tablo = karsilastir(kisiler, gunler, bordro, manuel)
        excel_yaz(tablo, ROOT / "cikti" / f"karsilastirma_{ay}.xlsx")

        print(f"== {ay}: ÜRETİM {ozet(tablo)} | İDARİ {ozet(tablo, 'İDARİ')}")
