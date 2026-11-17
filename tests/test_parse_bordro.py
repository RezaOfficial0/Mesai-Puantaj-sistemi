from pathlib import Path
import pytest

from parse_bordro import parse_bordro, saat_metni_to_dk

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
AYLAR = ["bordrolama Ağustos.xls", "Bordrolama eylül.xls", "Bordrolama ekim.xls"]


def test_saat_metni():
    assert saat_metni_to_dk("132 Saat") == 7920
    assert saat_metni_to_dk("88.5 Saat") == 5310
    assert saat_metni_to_dk("") == 0
    with pytest.raises(ValueError):
        saat_metni_to_dk("abc")


@pytest.mark.parametrize("dosya", AYLAR)
def test_ozet_satiri_tutuyor(dosya):
    bordro, ozet = parse_bordro(RAW / dosya)
    assert len(bordro) == ozet["kisi"]
    assert bordro["gun"].sum() == ozet["gun"]
    assert bordro["fm_dk"].sum() == ozet["fm_dk"]
    assert bordro["ht_dk"].sum() == ozet["ht_dk"]


def test_ekim_degerleri():
    bordro, ozet = parse_bordro(RAW / "Bordrolama ekim.xls")
    assert ozet == {"gun": 2031.0, "fm_dk": 245310, "ht_dk": 13680, "kisi": 75}
