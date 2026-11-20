from pathlib import Path

import pandas as pd
import pytest

from on_tablo import ISTISNA_TURLERI, excel_yaz, hatali_eslesme, on_tablo
from parse_genel import parse_genel
from parse_puantaj import parse_puantaj
from tatiller import tatil_oku

KOK = Path(__file__).resolve().parent.parent
RAW = KOK / "data" / "raw"
KASIM = RAW / "giriş çıkış 01.11.2026 - 15.11.2026.xlsm"


@pytest.fixture(scope="module")
def kasim():
    referans, _ = parse_puantaj(RAW / "ekim yüz okuma.xls")
    return parse_genel(KASIM, referans)


@pytest.fixture(scope="module")
def sonuc(kasim):
    kisiler, gunler = kasim
    return on_tablo(kisiler, gunler, tatil_oku())


def test_hatali_eslesme_ornekler():
    g = pd.DataFrame({
        "vardiya": ["İDARİ HAFTA İÇİ", "HAFTA İÇİ 19-07", "HAFTA İÇİ 07-15", "HAFTA İÇİ 23-07", "İDARİ HAFTA İÇİ"],
        "giris_dk": pd.array([1080, 1140, 401, 1380, 507], dtype="Int64"),
        "cikis_dk": pd.array([484, 420, 1141, 420, None], dtype="Int64"),
    })
    assert hatali_eslesme(g).tolist() == [True, False, False, False, False]


def test_idari_1230_hepsi_yakalaniyor(sonuc):
    _, ist, g = sonuc
    idari_1230 = g[g["hesap_grubu"].str.contains("İDARİ") & g["fazla_mesai_dk"].eq(750)]
    hatali = ist[ist["kod"] == "HATALI_ESLESME"]
    assert len(idari_1230) == 9
    assert set(zip(idari_1230["kart_no"], idari_1230["tarih"])) <= set(zip(hatali["kart_no"], hatali["tarih"]))


def test_istisna_sayilari(sonuc):
    _, ist, _ = sonuc
    sayim = ist["kod"].value_counts()
    assert sayim["EKSIK_CIKIS"] == 28
    assert sayim["EKSIK_GIRIS"] == 1
    assert sayim["UZUN_GUN"] == 14          # 07:00-19:1x gibi normal 12 saatlik günler sayılmaz
    assert set(ist["kod"]) <= set(ISTISNA_TURLERI)


def test_uzun_gun_esigi(sonuc):
    _, _, g = sonuc
    uzun = g["istisna"].fillna("").str.contains("UZUN_GUN")
    assert (g.loc[uzun, "calisma_dk"] >= 735).all()
    assert (g.loc[~uzun & ~g["istisna"].fillna("").str.contains("HATALI"), "calisma_dk"] < 735).all()


def test_kisi_ozeti(sonuc):
    oz, ist, _ = sonuc
    assert len(oz) == 72 and oz["kart_no"].is_unique
    assert (oz["fm_kesintisiz_dk"] >= 0).all() and (oz["fm_kesintisiz_dk"] % 30 == 0).all()
    assert (oz["fm_kesintili_dk"] <= oz["fm_kesintisiz_dk"]).all()
    idari = oz["hesap_grubu"].str.contains("İDARİ")
    assert (oz.loc[idari, "fm_kesintisiz_dk"] == 0).all()
    assert set(ist["kart_no"]) <= set(oz["kart_no"])
    # Eksi bakiye ve devamsızlık kişi bazında en fazla bir kez
    kisi_bazli = ist[ist["kod"].isin(["EKSI_BAKIYE", "DEVAMSIZLIK_KARARI"])]
    assert not kisi_bazli.duplicated(["kart_no", "kod"]).any()
    assert set(oz.loc[oz["bizim_fm_dk"] < 0, "kart_no"]) == set(ist.loc[ist["kod"] == "EKSI_BAKIYE", "kart_no"])


def test_deterministik_ve_ham_veri_degismiyor(kasim):
    kisiler, gunler = kasim
    once = gunler.copy()
    a = on_tablo(kisiler, gunler, tatil_oku())
    b = on_tablo(kisiler, gunler, tatil_oku())
    pd.testing.assert_frame_equal(gunler, once)
    pd.testing.assert_frame_equal(a[0], b[0])
    pd.testing.assert_frame_equal(a[1], b[1])


def test_excel(sonuc, tmp_path):
    oz, ist, g = sonuc
    yol = tmp_path / "on_tablo.xlsx"
    excel_yaz(oz, ist, g, KASIM, yol)
    sayfalar = pd.read_excel(yol, sheet_name=None)
    assert list(sayfalar) == ["Kişi Özeti", "İstisnalar", "Günlük Detay", "Kurallar"]
    assert len(sayfalar["Kişi Özeti"]) == 72
    assert len(sayfalar["İstisnalar"]) == len(ist)
    assert len(sayfalar["Günlük Detay"]) == 1078
