from pathlib import Path
import pandas as pd
import pytest

from parse_puantaj import parse_puantaj
from parse_bordro import parse_bordro
from eslestir import manuel_oku
from karsilastir import karsilastir, ozet
from rules import _yuvarla, gunluk_mesai, aylik_son_islem

KOK = Path(__file__).resolve().parent.parent
RAW = KOK / "data" / "raw"
MANUEL = KOK / "config" / "eslestirme.csv"


def test_yuvarlama():
    s = pd.Series([0, 14, 15, 44, 45, 240, 242])
    assert _yuvarla(s).tolist() == [0, 0, 30, 30, 60, 240, 240]


def _olc(p_dosya, b_dosya):
    kisiler, gunler = parse_puantaj(RAW / p_dosya)
    bordro, _ = parse_bordro(RAW / b_dosya)
    t = karsilastir(kisiler, gunler, bordro, manuel_oku(MANUEL),
                    kural=gunluk_mesai, son_islem=lambda t, g: aylik_son_islem(t, g, "gun_30"))
    return t, ozet(t)


@pytest.mark.parametrize("p_dosya, b_dosya, min_tam", [
    ("ağustos yüz okuma.xls", "bordrolama Ağustos.xls", 46),
    ("eylül yüz okuma.xls", "Bordrolama eylül.xls", 51),
])
def test_kural_v1_basarisi(p_dosya, b_dosya, min_tam):
    """Kural değişikliği bu sayıları düşürürse test kırmızıya döner."""
    t, o = _olc(p_dosya, b_dosya)
    assert o["tam"] >= min_tam


def test_idari_sifir():
    t, _ = _olc("ekim yüz okuma.xls", "Bordrolama ekim.xls")
    assert (t.loc[t["hesap_grubu"].str.contains("İDARİ"), "bizim_dk"] == 0).all()


def test_mesai_eksi_olmaz():
    t, _ = _olc("ekim yüz okuma.xls", "Bordrolama ekim.xls")
    assert (t["bizim_dk"] >= 0).all()
