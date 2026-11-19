from pathlib import Path
import pytest

from parse_puantaj import parse_puantaj
from parse_bordro import parse_bordro
from eslestir import norm_ad, eslestir, manuel_oku, yakin_oneriler

KOK = Path(__file__).resolve().parent.parent
RAW = KOK / "data" / "raw"
MANUEL = KOK / "config" / "eslestirme.csv"

AYLAR = [
    # puantaj, bordro, eşleşen, puantajda kalan, bordroda kalan
    ("ağustos yüz okuma.xls", "bordrolama Ağustos.xls", 76, 4, 2),
    ("eylül yüz okuma.xls", "Bordrolama eylül.xls", 76, 2, 2),
    ("ekim yüz okuma.xls", "Bordrolama ekim.xls", 71, 2, 2),
]


def test_norm_ad():
    assert norm_ad("Yunus Selvi") == "YUNUS SELVİ"
    assert norm_ad("ADNAN  BAL ") == "ADNAN BAL"
    assert norm_ad("ışık ilkay") == "IŞIK İLKAY"


def test_manuel_kart_no_sifirlari_korunuyor():
    manuel = manuel_oku(MANUEL)
    assert manuel["kart_no"].str.len().eq(5).all()


@pytest.mark.parametrize("p_dosya, b_dosya, n_eslesen, n_p_kalan, n_b_kalan", AYLAR)
def test_eslestirme_sayilari(p_dosya, b_dosya, n_eslesen, n_p_kalan, n_b_kalan):
    kisiler, _ = parse_puantaj(RAW / p_dosya)
    bordro, _ = parse_bordro(RAW / b_dosya)
    eslesme, p_kalan, b_kalan = eslestir(kisiler, bordro, manuel_oku(MANUEL))
    assert len(eslesme) == n_eslesen
    assert len(p_kalan) == n_p_kalan
    assert len(b_kalan) == n_b_kalan
    assert eslesme["kart_no"].is_unique


def test_manuel_olmadan_ekim():
    kisiler, _ = parse_puantaj(RAW / "ekim yüz okuma.xls")
    bordro, _ = parse_bordro(RAW / "Bordrolama ekim.xls")
    eslesme, p_kalan, b_kalan = eslestir(kisiler, bordro)
    assert (len(eslesme), len(p_kalan), len(b_kalan)) == (64, 9, 9)
    assert len(yakin_oneriler(p_kalan, b_kalan)) == 6
