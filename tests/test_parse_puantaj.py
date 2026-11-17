from pathlib import Path
import pandas as pd
import pytest

from parse_puantaj import parse_puantaj, read_tables, pair_tables, clean_days, saat_to_dk

KOK = Path(__file__).resolve().parent.parent
RAW = KOK / "data" / "raw"
EKIM = RAW / "puantaj.xls"
AYLAR = ["ağustos yüz okuma.xls", "eylül yüz okuma.xls", "ekim yüz okuma.xls"]


@pytest.fixture(scope="module")
def ekim():
    return parse_puantaj(EKIM)


def test_kisi_sayisi(ekim):
    kisiler, gunler = ekim
    assert len(kisiler) == 73


def test_sirket_dagilimi(ekim):
    kisiler, gunler = ekim
    sayim = kisiler["sirket"].value_counts()
    assert sayim["MERKEZ"] == 55
    assert sayim["ŞUBE"] == 18


def test_gun_sayisi(ekim):
    kisiler, gunler = ekim
    assert len(gunler) == 2263


def test_kart_no_benzersiz_ve_5_haneli(ekim):
    kisiler, gunler = ekim
    assert kisiler["kart_no"].is_unique
    assert kisiler["kart_no"].str.len().eq(5).all()


def test_1230_hatasi_sayisi(ekim):
    kisiler, gunler = ekim
    assert (gunler["fazla_mesai_dk"] == 750).sum() == 16


@pytest.mark.parametrize("dosya", AYLAR)
def test_tum_aylar_toplam_tutuyor(dosya):
    for header, days in pair_tables(read_tables(RAW / dosya)):
        assert days.shape[1] == 10, f"{dosya} {header['Adı']}: tablo {days.shape[1]} sütun"
        temiz, toplam = clean_days(days, header["Kart No"])
        hesap = temiz["fazla_mesai_dk"].sum()
        beklenen = saat_to_dk(toplam["Fazla Mesai"].iloc[0]) or 0
        assert hesap == beklenen, f"{dosya} {header['Adı']} {header['Soyadı']}: {hesap} != {beklenen}"


@pytest.mark.parametrize("dosya", AYLAR)
def test_her_gun_tek_satir(dosya):
    kisiler, gunler = parse_puantaj(RAW / dosya)
    assert not gunler.duplicated(["kart_no", "tarih"]).any()
