"""
Tahmin yontemi turnuvasi - cok haftali backtest.
Son N haftayi tek tek 'gelecekmis gibi' tahmin edip her yontemin
ortalama WAPE/MAE/bias degerini verir. main.py'yi ETKILEMEZ.
"""

import os
import numpy as np
import pandas as pd
from data_loader import load_all
import lightgbm as lgb


def y_agirlikli_medyan(egitim, test_satir, n=14):
    """Yakin haftalara daha cok agirlik veren medyan."""
    gd = {ad: g for ad, g in egitim.groupby(["Çıkış Transfer Merkezi", "Varış Transfer Merkezi"])}
    out = []
    for (c, v, t, _) in test_satir:
        g = gd.get((c, v))
        if g is None: out.append(0.0); continue
        son = _ayni_gun_son(g, t.dayofweek, n)
        if len(son) == 0: out.append(g["Toplam Desi"].median()); continue
        w = np.arange(1, len(son) + 1)  # eski->yeni artan agirlik
        # agirlikli medyan
        sira = np.argsort(son); s_son = son[sira]; s_w = w[sira]
        cum = np.cumsum(s_w); kesim = cum[-1] / 2.0
        idx = np.searchsorted(cum, kesim)
        out.append(max(s_son[min(idx, len(s_son)-1)], 0))
    return out


def y_medyan_ort_karisim(egitim, test_satir, n=14, w_med=0.7):
    gd = {ad: g for ad, g in egitim.groupby(["Çıkış Transfer Merkezi", "Varış Transfer Merkezi"])}
    out = []
    for (c, v, t, _) in test_satir:
        g = gd.get((c, v))
        if g is None: out.append(0.0); continue
        son = _ayni_gun_son(g, t.dayofweek, n)
        if len(son) == 0: out.append(g["Toplam Desi"].mean()); continue
        w = np.arange(1, len(son) + 1)
        med = np.median(son); ort = np.average(son, weights=w)
        out.append(max(w_med * med + (1 - w_med) * ort, 0))
    return out


def y_geometrik(egitim, test_satir, n=14):
    gd = {ad: g for ad, g in egitim.groupby(["Çıkış Transfer Merkezi", "Varış Transfer Merkezi"])}
    out = []
    for (c, v, t, _) in test_satir:
        g = gd.get((c, v))
        if g is None: out.append(0.0); continue
        son = _ayni_gun_son(g, t.dayofweek, n)
        if len(son) == 0: out.append(g["Toplam Desi"].mean()); continue
        pozitif = son[son > 0]
        out.append(max(np.exp(np.mean(np.log(pozitif))), 0) if len(pozitif) else 0.0)
    return out


def y_huber(egitim, test_satir, n=14, k=1.5):
    """Huber M-estimator: medyan ile ortalama arasi saglam merkez."""
    gd = {ad: g for ad, g in egitim.groupby(["Çıkış Transfer Merkezi", "Varış Transfer Merkezi"])}
    def huber_loc(x, k=1.5, iter=20):
        mu = np.median(x)
        s = np.median(np.abs(x - mu)) * 1.4826 + 1e-9
        for _ in range(iter):
            r = (x - mu) / s
            w = np.clip(k / np.abs(r), None, 1.0)
            w[np.abs(r) <= k] = 1.0
            mu_yeni = np.sum(w * x) / np.sum(w)
            if abs(mu_yeni - mu) < 1e-6: break
            mu = mu_yeni
        return mu
    out = []
    for (c, v, t, _) in test_satir:
        g = gd.get((c, v))
        if g is None: out.append(0.0); continue
        son = _ayni_gun_son(g, t.dayofweek, n)
        out.append(max(huber_loc(son, k), 0) if len(son) else g["Toplam Desi"].median())
    return out


def y_kuantil(egitim, test_satir, n=14, q=0.45):
    gd = {ad: g for ad, g in egitim.groupby(["Çıkış Transfer Merkezi", "Varış Transfer Merkezi"])}
    out = []
    for (c, v, t, _) in test_satir:
        g = gd.get((c, v))
        if g is None: out.append(0.0); continue
        son = _ayni_gun_son(g, t.dayofweek, n)
        out.append(max(np.quantile(son, q), 0) if len(son) else g["Toplam Desi"].median())
    return out

def y_medyan_bias(egitim, test_satir, n=14):
    """Medyan + rota bazli bias duzeltme."""
    gd = {ad: g for ad, g in egitim.groupby(["Çıkış Transfer Merkezi", "Varış Transfer Merkezi"])}

    # Her rota icin gecmis bias olc (medyan tahmin - gercek)
    bias_map = {}
    for rota, g in gd.items():
        g = g.sort_values("Tarih")
        if len(g) < 21: bias_map[rota] = 0.0; continue
        hatalar = []
        for _, r in g.tail(28).iterrows():
            gecmis = g[g["Tarih"] < r["Tarih"]]
            son = _ayni_gun_son(gecmis, r["Tarih"].dayofweek, n)
            if len(son): hatalar.append(np.median(son) - r["Toplam Desi"])
        bias_map[rota] = np.median(hatalar) if hatalar else 0.0

    out = []
    for (c, v, t, _) in test_satir:
        g = gd.get((c, v))
        if g is None: out.append(0.0); continue
        son = _ayni_gun_son(g, t.dayofweek, n)
        tah = np.median(son) if len(son) else g["Toplam Desi"].median()
        out.append(max(tah - bias_map.get((c, v), 0.0), 0))
    return out


def y_adaptif(egitim, test_satir, n=14):
    """Her rota icin gecmiste daha iyi olani (ortalama/medyan) sec."""
    gd = {ad: g for ad, g in egitim.groupby(["Çıkış Transfer Merkezi", "Varış Transfer Merkezi"])}

    # Her rota icin: gecmiste ortalama mi medyan mi daha dusuk hata vermis?
    secim = {}
    for rota, g in gd.items():
        g = g.sort_values("Tarih")
        if len(g) < 21: secim[rota] = "medyan"; continue
        e_ort, e_med = [], []
        for _, r in g.tail(28).iterrows():
            gecmis = g[g["Tarih"] < r["Tarih"]]
            son = _ayni_gun_son(gecmis, r["Tarih"].dayofweek, n)
            if len(son) == 0: continue
            w = np.arange(1, len(son) + 1)
            e_ort.append(abs(np.average(son, weights=w) - r["Toplam Desi"]))
            e_med.append(abs(np.median(son) - r["Toplam Desi"]))
        secim[rota] = "ortalama" if (e_ort and np.mean(e_ort) < np.mean(e_med)) else "medyan"

    out = []
    for (c, v, t, _) in test_satir:
        g = gd.get((c, v))
        if g is None: out.append(0.0); continue
        son = _ayni_gun_son(g, t.dayofweek, n)
        if len(son) == 0: out.append(g["Toplam Desi"].mean()); continue
        if secim.get((c, v)) == "ortalama":
            w = np.arange(1, len(son) + 1)
            out.append(max(np.average(son, weights=w), 0))
        else:
            out.append(max(np.median(son), 0))
    return out

def _ayni_gun_son(grup, dow, n):
    ayni = grup[grup["Tarih"].dt.dayofweek == dow].sort_values("Tarih")
    return ayni.tail(n)["Toplam Desi"].values


def y_medyan(egitim, test_satir, n=14):
    gd = {ad: g for ad, g in egitim.groupby(["Çıkış Transfer Merkezi", "Varış Transfer Merkezi"])}
    out = []
    for (c, v, t, _) in test_satir:
        g = gd.get((c, v))
        if g is None: out.append(0.0); continue
        son = _ayni_gun_son(g, t.dayofweek, n)
        out.append(max(np.median(son), 0) if len(son) else g["Toplam Desi"].median())
    return out


def y_trimmed(egitim, test_satir, n=14, kirp=0.2):
    gd = {ad: g for ad, g in egitim.groupby(["Çıkış Transfer Merkezi", "Varış Transfer Merkezi"])}
    out = []
    for (c, v, t, _) in test_satir:
        g = gd.get((c, v))
        if g is None: out.append(0.0); continue
        son = np.sort(_ayni_gun_son(g, t.dayofweek, n))
        if len(son) == 0: out.append(g["Toplam Desi"].mean()); continue
        k = int(len(son) * kirp)
        kesit = son[k:len(son)-k] if len(son) - 2*k > 0 else son
        out.append(max(np.mean(kesit), 0))
    return out


def y_ewma(egitim, test_satir, n=14, alpha=0.3):
    gd = {ad: g for ad, g in egitim.groupby(["Çıkış Transfer Merkezi", "Varış Transfer Merkezi"])}
    out = []
    for (c, v, t, _) in test_satir:
        g = gd.get((c, v))
        if g is None: out.append(0.0); continue
        son = _ayni_gun_son(g, t.dayofweek, n)
        if len(son) == 0: out.append(g["Toplam Desi"].mean()); continue
        # ustel agirlik: en yeni en agir
        w = np.array([(1 - alpha) ** (len(son) - 1 - i) for i in range(len(son))])
        out.append(max(np.average(son, weights=w), 0))
    return out


def y_trend(egitim, test_satir, n=14):
    """Mevsimsel ortalama + son haftalarin egimi (lineer trend)."""
    gd = {ad: g for ad, g in egitim.groupby(["Çıkış Transfer Merkezi", "Varış Transfer Merkezi"])}
    out = []
    for (c, v, t, _) in test_satir:
        g = gd.get((c, v))
        if g is None: out.append(0.0); continue
        son = _ayni_gun_son(g, t.dayofweek, n)
        if len(son) < 3: 
            out.append(max(np.mean(son), 0) if len(son) else g["Toplam Desi"].mean()); continue
        x = np.arange(len(son))
        egim, sabit = np.polyfit(x, son, 1)   # lineer fit
        tahmin = egim * len(son) + sabit       # bir sonraki nokta
        out.append(max(tahmin, 0))
    return out

def _ozellik_uret(desi):
    df = desi.copy().sort_values(["Çıkış Transfer Merkezi", "Varış Transfer Merkezi", "Tarih"])
    df["rota"] = df["Çıkış Transfer Merkezi"] + "->" + df["Varış Transfer Merkezi"]
    df["dow"] = df["Tarih"].dt.dayofweek
    df["gun"] = df["Tarih"].dt.day
    df["ay"] = df["Tarih"].dt.month
    df["haftasonu"] = (df["dow"] >= 5).astype(int)
    g = df.groupby("rota")["Toplam Desi"]
    df["lag1"] = g.shift(1)
    df["lag7"] = g.shift(7)
    df["lag14"] = g.shift(14)
    df["roll7"] = g.shift(1).rolling(7).mean().reset_index(0, drop=True)
    df["roll28"] = g.shift(1).rolling(28).mean().reset_index(0, drop=True)
    # Mevsimsel ozellik: ayni haftanin gununun gecmis ortalamasi (sizinti yok, shift'li)
    df["dow_avg"] = (df.groupby(["rota", "dow"])["Toplam Desi"]
                       .transform(lambda s: s.shift(1).expanding().mean()))
    df["rota_kod"] = df["rota"].astype("category").cat.codes
    return df


_LGB_OZ = ["rota_kod", "dow", "gun", "ay", "haftasonu",
           "lag1", "lag7", "lag14", "roll7", "roll28", "dow_avg"]


def y_lightgbm(egitim, test_satir):
    # Egitim + test'i birlikte ozellik uret (lag'ler icin gerekli), sonra ayir
    test_df = pd.DataFrame(test_satir, columns=["Çıkış Transfer Merkezi", "Varış Transfer Merkezi", "Tarih", "Toplam Desi"])
    tum = pd.concat([egitim, test_df], ignore_index=True)
    feat = _ozellik_uret(tum)

    test_tarih = test_df["Tarih"].min()
    egit = feat[feat["Tarih"] < test_tarih].dropna(subset=_LGB_OZ)
    tst = feat[feat["Tarih"] >= test_tarih].copy()

    # Log donusumu (talep carpik)
    y = np.log1p(egit["Toplam Desi"].clip(lower=0))
    model = lgb.LGBMRegressor(
        n_estimators=600, learning_rate=0.03, num_leaves=63,
        min_child_samples=30, subsample=0.8, colsample_bytree=0.8,
        random_state=42, verbose=-1
    )
    model.fit(egit[_LGB_OZ], y)
    pred = np.expm1(model.predict(tst[_LGB_OZ]))
    return list(np.maximum(pred, 0))


def yap_hibrit(yontem_a, yontem_b):
    """Iki yontemin ortalamasi."""
    def f(egitim, test_satir):
        a = np.array(yontem_a(egitim, test_satir))
        b = np.array(yontem_b(egitim, test_satir))
        return list((a + b) / 2)
    return f

# ---------- Metrik ----------
def skorla(gercek, tahmin):
    g = np.array(gercek, float); t = np.array(tahmin, float)
    hata = t - g
    return {
        "MAE": np.mean(np.abs(hata)),
        "WAPE": np.sum(np.abs(hata)) / np.sum(g) * 100,
        "Bias": np.mean(hata),
    }


# ---------- Yontemler ----------
# Her yontem: (egitim_df, test_satirlari) -> tahmin listesi
def y_agirlikli(egitim, test_satir, son_n_hafta=6):
    grup_dict = {ad: g for ad, g in egitim.groupby(["Çıkış Transfer Merkezi", "Varış Transfer Merkezi"])}
    out = []
    for (cikis, varis, tarih, _) in test_satir:
        g = grup_dict.get((cikis, varis))
        if g is None:
            out.append(0.0); continue
        ayni = g[g["Tarih"].dt.dayofweek == tarih.dayofweek].sort_values("Tarih")
        if len(ayni) == 0:
            out.append(g["Toplam Desi"].mean()); continue
        son = ayni.tail(son_n_hafta)["Toplam Desi"].values
        w = np.arange(1, len(son) + 1)
        out.append(max(np.average(son, weights=w), 0))
    return out


def y_agirlikli_bias(egitim, test_satir, son_n_hafta=6):
    """Agirlikli ortalama + rota bazli bias duzeltme.
    Her rotanin gecmisteki (tahmin - gercek) ortalama hatasini telafi eder."""
    grup_dict = {ad: g for ad, g in egitim.groupby(["Çıkış Transfer Merkezi", "Varış Transfer Merkezi"])}

    # Her rota icin gecmis bias: egitim setinin son haftalarinda
    # ayni-gun-ortalamasi ile gercek arasindaki ortalama fark
    bias_map = {}
    for rota, g in grup_dict.items():
        g = g.sort_values("Tarih")
        if len(g) < 14:
            bias_map[rota] = 0.0; continue
        hatalar = []
        for _, r in g.tail(28).iterrows():  # son 4 hafta uzerinden bias olc
            gecmis = g[g["Tarih"] < r["Tarih"]]
            ayni = gecmis[gecmis["Tarih"].dt.dayofweek == r["Tarih"].dayofweek]
            if len(ayni) == 0: continue
            son = ayni.tail(son_n_hafta)["Toplam Desi"].values
            w = np.arange(1, len(son) + 1)
            tah = np.average(son, weights=w)
            hatalar.append(tah - r["Toplam Desi"])  # +: fazla, -: az tahmin
        bias_map[rota] = np.mean(hatalar) if hatalar else 0.0

    out = []
    for (cikis, varis, tarih, _) in test_satir:
        g = grup_dict.get((cikis, varis))
        if g is None:
            out.append(0.0); continue
        ayni = g[g["Tarih"].dt.dayofweek == tarih.dayofweek].sort_values("Tarih")
        if len(ayni) == 0:
            out.append(g["Toplam Desi"].mean()); continue
        son = ayni.tail(son_n_hafta)["Toplam Desi"].values
        w = np.arange(1, len(son) + 1)
        tah = np.average(son, weights=w)
        tah_duz = tah - bias_map.get((cikis, varis), 0.0)  # biasi geri al
        out.append(max(tah_duz, 0))
    return out


def yap_pencere(n):
    def f(egitim, test_satir):
        return y_agirlikli(egitim, test_satir, son_n_hafta=n)
    return f


# ---------- Cok haftali backtest ----------
def turnuva(desi, yontemler, hafta_sayisi=4):
    son_tarih = desi["Tarih"].max()
    sonuc = {ad: [] for ad in yontemler}

    for h in range(hafta_sayisi):
        test_bit = son_tarih - pd.Timedelta(days=7 * h)
        test_bas = test_bit - pd.Timedelta(days=6)
        egitim = desi[desi["Tarih"] < test_bas]
        test = desi[(desi["Tarih"] >= test_bas) & (desi["Tarih"] <= test_bit)]
        test_satir = [(r["Çıkış Transfer Merkezi"], r["Varış Transfer Merkezi"], r["Tarih"], r["Toplam Desi"])
                      for _, r in test.iterrows()]
        gercek = [s[3] for s in test_satir]

        for ad, fn in yontemler.items():
            tah = fn(egitim, test_satir)
            sonuc[ad].append(skorla(gercek, tah))

    # ortalama
    print(f"=== TURNUVA ({hafta_sayisi} hafta ortalamasi) ===\n")
    print(f"{'Yontem':30s} | {'WAPE':>7s} | {'MAE':>8s} | {'Bias':>9s}")
    print("-" * 62)
    ozet = {}
    for ad, skorlar in sonuc.items():
        wape = np.mean([s["WAPE"] for s in skorlar])
        mae = np.mean([s["MAE"] for s in skorlar])
        bias = np.mean([s["Bias"] for s in skorlar])
        ozet[ad] = wape
        print(f"{ad:30s} | {wape:6.2f}% | {mae:8.1f} | {bias:+9.1f}")
    en_iyi = min(ozet, key=ozet.get)
    print(f"\n>>> En dusuk WAPE: {en_iyi} ({ozet[en_iyi]:.2f}%)")


if __name__ == "__main__":
    config_yolu = os.path.join(os.path.dirname(__file__), "..", "config.json")
    data = load_all(config_yolu)

    yontemler = {
        "Kuantil %25 14h": lambda e, t: y_kuantil(e, t, 14, 0.25),
        "Kuantil %28 14h": lambda e, t: y_kuantil(e, t, 14, 0.28),
        "Kuantil %30 14h": lambda e, t: y_kuantil(e, t, 14, 0.30),
        "Kuantil %32 14h": lambda e, t: y_kuantil(e, t, 14, 0.32),
        "Kuantil %35 14h": lambda e, t: y_kuantil(e, t, 14, 0.35),
    }
    turnuva(data["desi"], yontemler, hafta_sayisi=4)