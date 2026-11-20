from pathlib import Path

import pandas as pd
import pytest

from parse_puantaj import parse_puantaj
from parse_bordro import parse_bordro
from eslestir import manuel_oku
from karsilastir import karsilastir, ozet
from rules import gunluk_mesai_tatilli, aylik_son_islem
from tatiller import tatil_oku

KOK = Path(__file__).resolve().parent.parent
RAW = KOK / "data" / "raw"
MANUEL = KOK / "config" / "eslestirme.csv"


@pytest.fixture(scope="module")
def tatiller():
    return tatil_oku(RAW / "2026-excel-takvimi-resmi-tatiller.xlsx")


def test_tatil_oku(tatiller):
    assert len(tatiller) == 17
    assert tatiller["arife"].sum() == 3
    arife = tatiller.set_index("tarih").loc["2026-10-28"]
    assert arife["baslangic"] == pd.Timestamp("2026-10-28 12:30")
    assert arife["bitis"] == pd.Timestamp("2026-10-29 00:00")
    tam = tatiller.set_index("tarih").loc["2026-10-29"]
    assert tam["baslangic"] == pd.Timestamp("2026-10-29 00:00")


def test_takvim_puantaj_etiketleriyle_ayni(tatiller):
    """Ekim: takvimdeki tatil günleri puantajın RESMİ TATİL etiketleriyle aynı olmalı."""
    _, gunler = parse_puantaj(RAW / "ekim yüz okuma.xls")
    resmi = gunler[gunler["tatil"].fillna("").str.contains("RESMİ")]
    etiket = resmi.groupby("tarih")["tatil"].first()
    ekim = tatiller[tatiller["tarih"].dt.month == 10].set_index("tarih")
    assert list(etiket.index) == list(ekim.index)
    assert (etiket.str.contains("12:30") == ekim["arife"]).all()


def _gun(tarih, giris, cikis, vardiya="HAFTA İÇİ 07-15", fm=None, tatil=None, grup="ÜRETİM YENİ"):
    dk = lambda s: None if s is None else int(s[:2]) * 60 + int(s[3:])
    return {
        "tarih": pd.Timestamp(tarih), "giris_dk": dk(giris), "cikis_dk": dk(cikis),
        "giris_2_dk": None, "cikis_2_dk": None, "vardiya": vardiya, "tatil": tatil,
        "hesap_grubu": grup, "fazla_mesai_dk": fm, "erken_cikma_dk": None, "gec_gelme_dk": None,
    }


def test_tatil_mesaisi_ornekler(tatiller):
    g = pd.DataFrame([
        _gun("2026-10-28", "06:41", "19:01", fm=241, tatil="RESMİ TATİL (12:30-23:59)"),   # 12:30-19:00
        _gun("2026-10-28", "18:43", "07:01", "HAFTA İÇİ 19-07", fm=241),                    # 19:00-07:00, erken gelme sayılmaz
        _gun("2026-10-28", "07:00", "12:30", fm=None),                                       # tatilden önce çıktı
        _gun("2026-08-30", "07:00", "19:00", "PAZAR 07-15", fm=720, tatil="HAFTA TATİLİ"),   # Pazar'a denk gelen bayram
        _gun("2026-10-27", "19:00", "07:00", "HAFTA İÇİ 19-07", fm=240),                    # arife öncesi gece: tatil değil
        _gun("2026-10-28", "08:14", "13:23", "İDARİ HAFTA İÇİ", grup="İDARİ"),
        _gun("2026-10-28", "06:31", None, fm=None),                                          # çıkış eksik
    ]).astype({c: "Int64" for c in ["giris_dk", "cikis_dk", "giris_2_dk", "cikis_2_dk",
                                    "fazla_mesai_dk", "erken_cikma_dk", "gec_gelme_dk"]})
    s = gunluk_mesai_tatilli(g, tatiller)
    assert s["ht_dk"].tolist() == [390, 720, 0, 0, 0, 0, 0]
    assert s["fm_dk"].tolist() == [0, 0, 0, 0, 240, 0, 0]


def _olc_v2(p_dosya, b_dosya, tatiller):
    kisiler, gunler = parse_puantaj(RAW / p_dosya)
    bordro, _ = parse_bordro(RAW / b_dosya)
    t = karsilastir(kisiler, gunler, bordro, manuel_oku(MANUEL),
                    kural=lambda g: gunluk_mesai_tatilli(g, tatiller),
                    son_islem=lambda t, g: aylik_son_islem(t, g, "gun_30"))
    return t, ozet(t)


def test_ekim_tatil_mesaisi(tatiller):
    """Ekim: tatil mesaisi kişi bazında bordronun 'hafta tatili' sütunuyla tutmalı.

    Bilinen 5 istisna (kâğıt düzeltme / bordroda mesaisi 0 olanlar):
    Zübeyt Yenigül, Emre Altun, İbrahim Altun, Sezai Gürsoy, Berke Akçora.
    """
    t, o = _olc_v2("ekim yüz okuma.xls", "Bordrolama ekim.xls", tatiller)
    assert o["tam_ht"] >= 53
    assert o["tam"] >= 27
    farkli = set(t.loc[t["fark_ht_dk"] != 0, "kart_no"])
    assert farkli <= {"00014", "00246", "00071", "00010", "00202"}


@pytest.mark.parametrize("p_dosya, b_dosya, min_tam", [
    ("ağustos yüz okuma.xls", "bordrolama Ağustos.xls", 46),
    ("eylül yüz okuma.xls", "Bordrolama eylül.xls", 51),
])
def test_kural_6_eski_aylari_bozmuyor(p_dosya, b_dosya, min_tam, tatiller):
    t, o = _olc_v2(p_dosya, b_dosya, tatiller)
    assert o["tam"] >= min_tam
    assert t["bizim_ht_dk"].sum() == 0          # Ağustos 30 Pazar'a denk geldi, Eylül'de tatil yok
