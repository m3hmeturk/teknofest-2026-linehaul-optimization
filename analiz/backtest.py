"""
Backtest - Mevcut tahmin yonteminin isabetini olcer.
Son 7 gunu (bilinmeyen gibi) tahmin eder, gercekle karsilastirir.
main.py ve ciktilari ETKILEMEZ - sadece analiz.
"""

import os
import numpy as np
import pandas as pd
from data_loader import load_all


def _hafta_gunu_ortalama(grup, hedef_gun, son_n_hafta=6):
    """forecast.py ile AYNI mantik."""
    ayni_gun = grup[grup["Tarih"].dt.dayofweek == hedef_gun].sort_values("Tarih")
    if len(ayni_gun) == 0:
        return grup["Toplam Desi"].mean() if len(grup) else 0.0
    son = ayni_gun.tail(son_n_hafta)["Toplam Desi"].values
    agirlik = np.arange(1, len(son) + 1)
    return float(np.average(son, weights=agirlik))


def backtest(desi, test_gun=7, son_n_hafta=6):
    """Son 'test_gun' gunu test setine ayirir, geri kalanla tahmin eder."""
    son_tarih = desi["Tarih"].max()
    test_baslangic = son_tarih - pd.Timedelta(days=test_gun - 1)

    egitim = desi[desi["Tarih"] < test_baslangic].copy()
    test = desi[desi["Tarih"] >= test_baslangic].copy()

    print(f"Egitim: {egitim['Tarih'].min().date()} -> {egitim['Tarih'].max().date()} ({egitim['Tarih'].nunique()} gun)")
    print(f"Test  : {test['Tarih'].min().date()} -> {test['Tarih'].max().date()} ({test['Tarih'].nunique()} gun)")

    egitim_gruplar = egitim.groupby(["Çıkış Transfer Merkezi", "Varış Transfer Merkezi"])
    grup_dict = {ad: g for ad, g in egitim_gruplar}

    kayitlar = []
    for _, r in test.iterrows():
        rota = (r["Çıkış Transfer Merkezi"], r["Varış Transfer Merkezi"])
        grup = grup_dict.get(rota)
        if grup is None:
            tahmin = 0.0
        else:
            tahmin = _hafta_gunu_ortalama(grup, r["Tarih"].dayofweek, son_n_hafta)
        kayitlar.append({
            "rota": f"{rota[0]}->{rota[1]}",
            "tarih": r["Tarih"].date(),
            "gercek": r["Toplam Desi"],
            "tahmin": max(tahmin, 0.0),
        })
    return pd.DataFrame(kayitlar)


def metrikler(df):
    g = df["gercek"].values
    t = df["tahmin"].values
    hata = t - g  # pozitif = fazla tahmin

    mae = np.mean(np.abs(hata))
    rmse = np.sqrt(np.mean(hata ** 2))
    # MAPE (sifir olmayan gercekler icin)
    maske = g > 1
    mape = np.mean(np.abs(hata[maske] / g[maske])) * 100

    fazla = np.sum(hata > 0)
    az = np.sum(hata < 0)
    ortalama_bias = np.mean(hata)

    print("\n=== TAHMIN ISABETI ===")
    print(f"MAE  (ort. mutlak hata)   : {mae:,.0f} desi")
    print(f"RMSE                      : {rmse:,.0f} desi")
    print(f"MAPE (ort. yuzde hata)    : {mape:.1f}%")
    print(f"\nBias (ort. sapma)         : {ortalama_bias:,.0f} desi  (+ ise fazla tahmin)")
    print(f"Fazla tahmin edilen satir : {fazla} / {len(df)}")
    print(f"Az tahmin edilen satir    : {az} / {len(df)}")

    # Toplam hacim karsilastirmasi
    print(f"\nToplam gercek desi : {g.sum():,.0f}")
    print(f"Toplam tahmin desi : {t.sum():,.0f}")
    print(f"Hacim farki        : {(t.sum()-g.sum()):,.0f} ({(t.sum()/g.sum()-1)*100:+.1f}%)")


if __name__ == "__main__":
    config_yolu = os.path.join(os.path.dirname(__file__), "..", "config.json")
    data = load_all(config_yolu)
    df = backtest(data["desi"], test_gun=7, son_n_hafta=6)
    metrikler(df)

    print("\nEn cok HATALI 5 rota-gun (mutlak):")
    df["mutlak_hata"] = (df["tahmin"] - df["gercek"]).abs()
    print(df.nlargest(5, "mutlak_hata")[["rota","tarih","gercek","tahmin"]].to_string(index=False))