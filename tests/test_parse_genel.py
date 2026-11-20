import datetime as dt
from pathlib import Path

import pandas as pd
import pytest

from parse_genel import oku_genel, parse_genel, time_to_dk
from parse_puantaj import parse_puantaj
from rules import gunluk_mesai_tatilli
from tatiller import tatil_oku

KOK = Path(__file__).resolve().parent.parent
RAW = KOK / "data" / "raw"
KASIM = RAW / "giriş çıkış 01.11.2026 - 15.11.2026.xlsm"


@pytest.fixture(scope="module")
def ekim():
    return parse_puantaj(RAW / "ekim yüz okuma.xls")


@pytest.fixture(scope="module")
def kasim(ekim):
    return parse_genel(KASIM, referans_kisiler=ekim[0])


def test_time_to_dk():
    assert time_to_dk(dt.time(8, 13)) == 493
    assert time_to_dk(None) is None
    with pytest.raises(ValueError):
        time_to_dk("08:13")


def test_boyutlar(kasim):
    kisiler, gunler = kasim
    assert len(kisiler) == 72
    assert len(gunler) == 1078
    assert gunler["tarih"].nunique() == 15
    assert not gunler.duplicated(["kart_no", "tarih"]).any()
    gunluk = gunler.groupby("tarih").size()
    assert (gunluk.iloc[:13] == 72).all() and (gunluk.iloc[13:] == 71).all()   # 00179 son iki günde yok


def test_sema_ekimle_ayni(kasim, ekim):
    """Kural motoru değişmeden çalışsın diye sütunlar ve tipler parse_puantaj ile birebir aynı."""
    kisiler, gunler = kasim
    e_kisiler, e_gunler = ekim
    assert list(gunler.columns) == list(e_gunler.columns)
    assert (gunler.dtypes == e_gunler.dtypes).all()
    assert list(kisiler.columns) == list(e_kisiler.columns)
    assert (kisiler.dtypes == e_kisiler.dtypes).all()


def test_ornek_satir(kasim):
    _, gunler = kasim
    s = gunler[(gunler["kart_no"] == "00005") & (gunler["tarih"] == "2026-11-02")].iloc[0]
    assert (s["giris_dk"], s["cikis_dk"], s["fazla_mesai_dk"]) == (6 * 60 + 36, 19 * 60, 240)
    assert (s["giris_manuel"], s["cikis_manuel"]) == (False, True)
    assert s["vardiya"] == "HAFTA İÇİ 07-15"


def test_dosyanin_kendi_ozetiyle_tutuyor():
    """Her günün 'N personel giriş yaptı / devamsız / izinli' satırı bizim sayımla aynı.

    PDKS mantığı: giriş VEYA çıkış basan 'giriş yaptı'; izinli = izin (devamsız hariç)
    + hafta tatilinde olup kart basmayan.
    """
    _, gunler, gun_ozet = oku_genel(KASIM)
    basti = gunler["giris_dk"].notna() | gunler["cikis_dk"].notna()
    devamsiz = gunler["izin"].eq("Devamsız")
    izinli = ~basti & ((gunler["izin"].notna() & ~devamsiz) | gunler["tatil"].notna())
    bizim = pd.DataFrame({"giris_yapti": basti, "devamsiz": devamsiz, "izinli": izinli,
                          "tarih": gunler["tarih"]}).groupby("tarih").sum()
    dosya = gun_ozet.set_index("tarih")[["giris_yapti", "devamsiz", "izinli"]]
    pd.testing.assert_frame_equal(bizim, dosya, check_dtype=False, check_index_type=False)


def test_kisi_bilgisi_referanstan(kasim, ekim):
    kisiler, _ = kasim
    assert kisiler["hesap_grubu"].notna().all()                  # 72 kişinin hepsi Ekim'de var
    ayrilan = set(ekim[0]["kart_no"]) - set(kisiler["kart_no"])
    assert ayrilan == {"00205"}                                   # Cumhur Ecer 31.10.2026'da çıkmış


def test_kural_motoru_kasimda_calisiyor(kasim):
    kisiler, gunler = kasim
    g = gunler.merge(kisiler[["kart_no", "hesap_grubu"]], on="kart_no", how="left")
    s = gunluk_mesai_tatilli(g, tatil_oku())
    assert len(s) == len(g)
    assert s["ht_dk"].sum() == 0                                  # 1-15 Kasım'da resmi tatil yok
    assert (s.loc[g["hesap_grubu"].str.contains("İDARİ"), "fm_dk"] == 0).all()
