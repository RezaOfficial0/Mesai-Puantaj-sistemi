from pathlib import Path
import pytest

from parse_puantaj import parse_puantaj
from parse_bordro import parse_bordro
from eslestir import manuel_oku
from karsilastir import karsilastir, ozet, AYLAR

KOK = Path(__file__).resolve().parent.parent
RAW = KOK / "data" / "raw"
MANUEL = KOK / "config" / "eslestirme.csv"


def _yukle(p_dosya, b_dosya):
    kisiler, gunler = parse_puantaj(RAW / p_dosya)
    bordro, _ = parse_bordro(RAW / b_dosya)
    return kisiler, gunler, bordro


@pytest.mark.parametrize("ay, p_dosya, b_dosya", AYLAR)
def test_her_kisi_bir_kez(ay, p_dosya, b_dosya):
    kisiler, gunler, bordro = _yukle(p_dosya, b_dosya)
    tablo = karsilastir(kisiler, gunler, bordro, manuel_oku(MANUEL))
    assert tablo["kart_no"].is_unique


@pytest.mark.parametrize("ay, p_dosya, b_dosya", AYLAR)
def test_bordro_toplami_kaybolmuyor(ay, p_dosya, b_dosya):
    """Eşleşen kişilerin bordro saati, bordro toplamından eşleşmeyenlerin saati çıkınca kalan miktara eşit olmalı."""
    kisiler, gunler, bordro = _yukle(p_dosya, b_dosya)
    tablo = karsilastir(kisiler, gunler, bordro, manuel_oku(MANUEL))
    toplam = bordro["fm_dk"].sum() + bordro["ht_dk"].sum()
    from eslestir import norm_ad
    eslesen_adlar = set(tablo["anahtar"])
    eslesmeyen = bordro[~bordro["ad_soyad"].map(norm_ad).isin(eslesen_adlar)]
    assert tablo["bordro_dk"].sum() == toplam - eslesmeyen["fm_dk"].sum() - eslesmeyen["ht_dk"].sum()


def test_baseline_ekim():
    """Ham puantaj kuralının Ekim sonucu. Kural motoru bu sayıları iyileştirmeli."""
    kisiler, gunler, bordro = _yukle("ekim yüz okuma.xls", "Bordrolama ekim.xls")
    o = ozet(karsilastir(kisiler, gunler, bordro, manuel_oku(MANUEL)))
    assert o["kisi"] == 58
    assert o["tam"] == 1


def test_kural_degistirilebiliyor():
    kisiler, gunler, bordro = _yukle("ekim yüz okuma.xls", "Bordrolama ekim.xls")
    sifir = karsilastir(kisiler, gunler, bordro, manuel_oku(MANUEL), kural=lambda g: g["fazla_mesai_dk"].fillna(0) * 0)
    assert sifir["bizim_dk"].sum() == 0
