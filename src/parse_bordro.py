from pathlib import Path
import re
import pandas as pd
import xlrd

ROOT = Path(__file__).resolve().parent.parent
BORDRO_FILE = ROOT / "data" / "raw" / "Bordrolama ekim.xls"
SAAT_METNI = re.compile(r"^([\d.,]+)\s*Saat$")


def saat_metni_to_dk(deger):
    """'132 Saat' -> 7920, '88.5 Saat' -> 5310, boş -> 0."""
    metin = str(deger).strip()
    if metin == "":
        return 0
    eslesme = SAAT_METNI.match(metin)
    if eslesme is None:
        raise ValueError(f"Beklenmeyen saat değeri: {metin!r}")
    saat = float(eslesme.group(1).replace(",", "."))
    return round(saat * 60)


def find_header_row(sheet):
    for r in range(sheet.nrows):
        if str(sheet.cell_value(r, 0)).strip() == "ADI SOYADI":
            return r
    raise ValueError("'ADI SOYADI' başlığı bulunamadı")


def find_columns(sheet, baslik_satiri):
    basliklar = [str(x).strip().lower() for x in sheet.row_values(baslik_satiri)]
    sutun = {"ad": 0, "gun": basliklar.index("gün")}
    if "fazla mesai" in basliklar:
        sutun["fm"] = basliklar.index("fazla mesai")
    else:
        sutun["fm"] = sutun["gun"] + 1      # Ağustos/Eylül: başlıksız sütun
    if "hafta tatili" in basliklar:
        sutun["ht"] = basliklar.index("hafta tatili")
    if "giriş tarihi" in basliklar:
        sutun["giris"] = basliklar.index("giriş tarihi")
    return sutun


def parse_bordro(route):
    sheet = xlrd.open_workbook(route).sheet_by_index(0)
    baslik = find_header_row(sheet)
    sutun = find_columns(sheet, baslik)

    satirlar = []
    ozet = None
    for r in range(baslik + 1, sheet.nrows):
        ad = str(sheet.cell_value(r, sutun["ad"])).strip()
        gun = sheet.cell_value(r, sutun["gun"])

        if ad == "" and gun == "":
            continue
        if ad == "" and isinstance(gun, float):
            ozet = {
                "gun": gun,
                "fm_dk": saat_metni_to_dk(sheet.cell_value(r, sutun["fm"])),
                "ht_dk": saat_metni_to_dk(sheet.cell_value(r, sutun["ht"])) if "ht" in sutun else 0,
            }
            continue
        if ad.startswith("Listelenen"):
            ozet["kisi"] = int(re.search(r"\d+", ad).group())
            break

        satirlar.append({
            "ad_soyad": ad,
            "ise_giris": sheet.cell_value(r, sutun["giris"]) if "giris" in sutun else None,
            "gun": gun,
            "fm_dk": saat_metni_to_dk(sheet.cell_value(r, sutun["fm"])),
            "ht_dk": saat_metni_to_dk(sheet.cell_value(r, sutun["ht"])) if "ht" in sutun else 0,
        })

    return pd.DataFrame(satirlar), ozet


if __name__ == "__main__":
    bordro, ozet = parse_bordro(BORDRO_FILE)
    print(bordro.shape)
    print(bordro.head())
    print(ozet)