import difflib
import pandas as pd

TR_BUYUK = str.maketrans("iı", "İI")



def norm_ad(metin) -> str:
    metin = str(metin)
    metin = metin.translate(TR_BUYUK)
    metin = metin.upper()
    metin = " ".join(metin.split())
    return metin


def eslestir(kisiler, bordro, manuel=None):
    p = kisiler.copy()
    b = bordro.copy()

    # 1) İki tabloya da "anahtar" sütunu ekle
    p["anahtar"] = (p["ad"] + " " + p["soyad"]).map(norm_ad)
    b["anahtar"] = b["ad_soyad"].map(norm_ad)              # bordroda isim tek sütunda: "ad_soyad"

    # 1b) Elle onaylanmış eşleşmeler: puantajdaki anahtarı bordrodaki adla değiştir
    if manuel is not None:
        harita = dict(zip(manuel["kart_no"], manuel["bordro_adi"].map(norm_ad)))
        p["anahtar"] = p["kart_no"].map(harita).fillna(p["anahtar"])

    # 2) Bordrodaki tekrar eden isimleri tekilleştir
    b_tekil = b.drop_duplicates("anahtar")

    # 3) Anahtar üzerinden birleştir
    eslesme = p.merge(b_tekil[["anahtar", "ad_soyad"]], on="anahtar", how="inner")

    # 4) Açıkta kalanları bul
    puantaj_kalan = p[~p["anahtar"].isin(b["anahtar"])]
    bordro_kalan = b_tekil[~b_tekil["anahtar"].isin(p["anahtar"])]

    eslesme = eslesme[["kart_no", "anahtar", "ad_soyad"]].rename(columns={"ad_soyad": "bordro_adi"})
    return eslesme, puantaj_kalan, bordro_kalan


def manuel_oku(yol):
    return pd.read_csv(yol, dtype=str)


def yakin_oneriler(puantaj_kalan, bordro_kalan, esik=0.8):
    adaylar = bordro_kalan["anahtar"].tolist()
    oneriler = []

    for _, satir in puantaj_kalan.iterrows():
        aranan = satir["anahtar"]
        bulunan = difflib.get_close_matches(aranan, adaylar, n=1, cutoff=esik)

        if bulunan:
            oran = difflib.SequenceMatcher(None, aranan, bulunan[0]).ratio()
            # 2) Öneriyi listeye ekle: kart_no, puantaj_adi, bordro_adi, oran
            oneriler.append({
                "kart_no": satir["kart_no"],
                "puantaj_adi": aranan,
                "bordro_adi": bulunan[0],
                "oran": round(oran, 2),
            })

    return pd.DataFrame(oneriler)

if __name__ == "__main__":
    from parse_puantaj import parse_puantaj, ROOT
    from parse_bordro import parse_bordro

    manuel = manuel_oku(ROOT / "config" / "eslestirme.csv")
    for puantaj_dosyasi, bordro_dosyasi in [
        ("ağustos yüz okuma.xls", "bordrolama Ağustos.xls"),
        ("eylül yüz okuma.xls", "Bordrolama eylül.xls"),
        ("ekim yüz okuma.xls", "Bordrolama ekim.xls"),
    ]:
        kisiler, _ = parse_puantaj(ROOT / "data" / "raw" / puantaj_dosyasi)
        bordro, _ = parse_bordro(ROOT / "data" / "raw" / bordro_dosyasi)

        eslesme, p_kalan, b_kalan = eslestir(kisiler, bordro, manuel)
        print(f"== {puantaj_dosyasi}: eşleşen {len(eslesme)}, puantajda kalan {len(p_kalan)}, bordroda kalan {len(b_kalan)}")
        print("   puantajda kalan:", p_kalan["anahtar"].tolist())
        print("   bordroda kalan :", b_kalan["anahtar"].tolist())

        oneriler = yakin_oneriler(p_kalan, b_kalan)
        if len(oneriler):
            print("   yeni öneriler:")
            print(oneriler.sort_values("oran", ascending=False).to_string())
