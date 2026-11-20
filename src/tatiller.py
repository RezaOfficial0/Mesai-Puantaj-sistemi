"""Resmi tatil takvimi.

Kaynak: data/raw/<yıl>-excel-takvimi-resmi-tatiller.xlsx (şirketin gönderdiği liste).
  - Tam gün tatil: 00:00 - 23:59
  - Arife (Süre = 0,5): öğlen 12:30 sonrası
Her tatil mutlak zaman aralığı olarak tutulur: [baslangic, bitis). Böylece gece
vardiyası gibi gün aşan çalışmalar doğrudan kesiştirilebilir.
"""
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
TATIL_FILE = ROOT / "data" / "raw" / "2026-excel-takvimi-resmi-tatiller.xlsx"
ARIFE_BASLANGIC_DK = 12 * 60 + 30      # 12:30


def tatil_oku(yol=TATIL_FILE):
    """Takvimi okur: tarih, ad, tur, baslangic, bitis (Timestamp)."""
    ham = pd.read_excel(yol)
    ham = ham[ham["Tarih"].notna()]
    tarih = pd.to_datetime(ham["Tarih"]).dt.normalize()
    sure = ham["Süre (gün)"].astype(float)
    if not sure.isin([0.5, 1.0]).all():
        raise ValueError(f"Beklenmeyen tatil süresi: {sorted(sure.unique())}")

    baslangic_dk = sure.map({1.0: 0, 0.5: ARIFE_BASLANGIC_DK})
    return pd.DataFrame({
        "tarih": tarih,
        "ad": ham["Tatil"].str.strip(),
        "tur": ham["Tür"].str.strip(),
        "arife": sure.eq(0.5),
        "baslangic": tarih + pd.to_timedelta(baslangic_dk, unit="min"),
        "bitis": tarih + pd.Timedelta(days=1),
    }).reset_index(drop=True)


def kesisim_dk(bas, bit, tatiller):
    """[bas, bit) çalışma aralığının tatil aralıklarıyla kesişen toplam dakikası."""
    toplam = pd.Timedelta(0)
    for t_bas, t_bit in zip(tatiller["baslangic"], tatiller["bitis"]):
        ust = min(bit, t_bit)
        alt = max(bas, t_bas)
        if ust > alt:
            toplam += ust - alt
    return int(toplam.total_seconds() // 60)


if __name__ == "__main__":
    print(tatil_oku().to_string())
