"""
Forecast karsilastirma: Mevcut agirlikli ortalama vs LightGBM.
Ayni backtest (son 7 gun) uzerinde MAE / WAPE / bias olcer.
main.py'yi ETKILEMEZ - sadece analiz.
"""

import os
import numpy as np
import pandas as pd
import lightgbm as lgb
from data_loader import load_all


# ---------- Metrikler ----------
def metrik(gercek, tahmin, ad):
    g = np.array(gercek, dtype=float)
    t = np.array(tahmin, dtype=float)
    hata = t - g
    mae = np.mean(np.abs(hata))
    wape = np.sum(np.abs(hata)) / np.sum(g) * 100   # agirlikli yuzde hata
    bias = np.mean(hata)
    print(f"{ad:28s} | MAE: {mae:8.1f} | WAPE: {wape:6.2f}% | Bias: {bias:+8.1f}")
    return mae, wape, bias


# ---------- Yontem 1: Mevcut agirlikli ortalama ----------
def tahmin_agirlikli(grup, hedef_gun, son_n_hafta=6):
    ayni_gun = grup[grup["Tarih"].dt.dayofweek == hedef_gun].sort_values("Tarih")
    if len(ayni_gun) == 0:
        return grup["Toplam Desi"].mean() if len(grup) else 0.0
    son = ayni_gun.tail(son_n_hafta)["Toplam Desi"].values
    agirlik = np.arange(1, len(son) + 1)
    return float(np.average(son, weights=agirlik))


# ---------- Yontem 2: LightGBM ozellikleri ----------
def ozellik_uret(desi):
    df = desi.copy().sort_values(["Çıkış Transfer Merkezi", "Varış Transfer Merkezi", "Tarih"])
    df["rota"] = df["Çıkış Transfer Merkezi"] + "->" + df["Varış Transfer Merkezi"]
    df["dow"] = df["Tarih"].dt.dayofweek
    df["gun"] = df["Tarih"].dt.day
    df["ay"] = df["Tarih"].dt.month
    df["haftasonu"] = (df["dow"] >= 5).astype(int)
    df["ay_haftasi"] = (df["Tarih"].dt.day - 1) // 7

    # Rota bazli lag ve rolling (gecmise bakan, sizinti yok)
    g = df.groupby("rota")["Toplam Desi"]
    df["lag1"] = g.shift(1)
    df["lag7"] = g.shift(7)
    df["lag14"] = g.shift(14)
    df["roll7"] = g.shift(1).rolling(7).mean().reset_index(0, drop=True)
    df["roll28"] = g.shift(1).rolling(28).mean().reset_index(0, drop=True)

    # Rota kategorik kodu
    df["rota_kod"] = df["rota"].astype("category").cat.codes
    return df


OZELLIKLER = ["rota_kod", "dow", "gun", "ay", "haftasonu", "ay_haftasi",
              "lag1", "lag7", "lag14", "roll7", "roll28"]


if __name__ == "__main__":
    config_yolu = os.path.join(os.path.dirname(__file__), "..", "config.json")
    data = load_all(config_yolu)
    desi = data["desi"]

    son_tarih = desi["Tarih"].max()
    test_bas = son_tarih - pd.Timedelta(days=6)
    print(f"Egitim: ... -> {(test_bas - pd.Timedelta(days=1)).date()}")
    print(f"Test  : {test_bas.date()} -> {son_tarih.date()}\n")

    # === YONTEM 1: Agirlikli ortalama ===
    egitim = desi[desi["Tarih"] < test_bas]
    test = desi[desi["Tarih"] >= test_bas]
    grup_dict = {ad: g for ad, g in egitim.groupby(["Çıkış Transfer Merkezi", "Varış Transfer Merkezi"])}
    tah1 = []
    for _, r in test.iterrows():
        rota = (r["Çıkış Transfer Merkezi"], r["Varış Transfer Merkezi"])
        grup = grup_dict.get(rota)
        tah1.append(max(tahmin_agirlikli(grup, r["Tarih"].dayofweek) if grup is not None else 0.0, 0))

    # === YONTEM 2: LightGBM ===
    tum = ozellik_uret(desi)
    egit = tum[tum["Tarih"] < test_bas].dropna(subset=OZELLIKLER)
    tst = tum[tum["Tarih"] >= test_bas].copy()

    model = lgb.LGBMRegressor(
        n_estimators=400, learning_rate=0.05, num_leaves=31,
        min_child_samples=20, subsample=0.8, colsample_bytree=0.8,
        random_state=42, verbose=-1
    )
    model.fit(egit[OZELLIKLER], egit["Toplam Desi"])
    tah2 = np.maximum(model.predict(tst[OZELLIKLER]), 0)

    # === SONUCLAR ===
    print("=== TAHMIN KARSILASTIRMASI (test: son 7 gun) ===")
    metrik(test["Toplam Desi"].values, tah1, "Mevcut (agirlikli ortalama)")
    metrik(tst["Toplam Desi"].values, tah2, "LightGBM")

    print("\nOzellik onemi (LightGBM):")
    onem = pd.Series(model.feature_importances_, index=OZELLIKLER).sort_values(ascending=False)
    print(onem.to_string())