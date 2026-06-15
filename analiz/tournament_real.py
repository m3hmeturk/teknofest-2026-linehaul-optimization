"""
Gercek-maliyet turnuvasi.
Her yontem icin: gecmis haftalarda tahmin -> plan kur -> GERCEK talebe karsi
maliyet + ihlal olc. Hakem metrigi: 'tahmininiz uzerinden kurdugunuz planin
gercek talebe karsi maliyeti' + 'tahmin basarisi'.
main.py'yi ETKILEMEZ.
"""

import os
import numpy as np
import pandas as pd
from collections import defaultdict
from data_loader import load_all
from distance_cost import build_all as build_costs
from optimizer import solve_spot
from statsmodels.tsa.holtwinters import ExponentialSmoothing
import warnings
warnings.filterwarnings("ignore")  # HW yakinsama uyarilarini sustur


def tahmin_holtwinters(grup, hedef_tarih, hafta_sayisi_geri=18):
    """Rotanin gunluk zaman serisinden Holt-Winters ile hedef gunu tahmin eder."""
    g = grup.sort_values("Tarih")
    # Hedef tarihten onceki son ~18 haftayi al (gunluk seri)
    bas = hedef_tarih - pd.Timedelta(weeks=hafta_sayisi_geri)
    seri = g[(g["Tarih"] >= bas) & (g["Tarih"] < hedef_tarih)].set_index("Tarih")["Toplam Desi"]
    seri = seri.asfreq("D")  # gunluk frekans
    seri = seri.interpolate().bfill().fillna(0)
    if len(seri) < 21 or seri.sum() == 0:
        # yetersiz veri -> son 14 gun ortalamasi
        return max(seri.tail(14).mean(), 0) if len(seri) else 0.0
    try:
        model = ExponentialSmoothing(
            seri, trend="add", seasonal="add", seasonal_periods=7,
            initialization_method="estimated"
        ).fit()
        # hedef gune kadar kac gun ileri tahmin gerekiyor
        ileri = (hedef_tarih - seri.index[-1]).days
        tahmin = model.forecast(ileri).iloc[-1]
        return max(float(tahmin), 0)
    except Exception:
        return max(seri.tail(14).mean(), 0)


def degerlendir_holtwinters(data, maliyet_df, k, hafta_sayisi=4, son_n_hafta=14):
    desi = data["desi"]
    arac_tipleri = list(data["arac"]["Araç Adı"])
    env = defaultdict(int)
    for _, r in data["kiralik"].iterrows():
        env[(r["Çıkış Transfer Merkezi"], r["Varış Transfer Merkezi"], r["Araç Türü"])] += int(r["Araç sayısı"])
    cost_by_rota = defaultdict(dict)
    for _, m in maliyet_df.iterrows():
        cost_by_rota[(m["cikis"], m["varis"])][m["arac_tipi"]] = {
            "kapasite": m["kapasite"], "kiralik_maliyet": m["kiralik_maliyet"], "spot_maliyet": m["spot_maliyet"]
        }

    def plan_mk(rota, planlanan):
        cr = cost_by_rota.get(rota, {})
        if not cr: return 0.0, 0.0
        kk = sum(cr[t]["kapasite"] * env.get((rota[0], rota[1], t), 0) for t in arac_tipleri if t in cr)
        km = sum(cr[t]["kiralik_maliyet"] * env.get((rota[0], rota[1], t), 0) for t in arac_tipleri if t in cr)
        residual = max(planlanan - kk, 0.0)
        spot = solve_spot(residual, cr, arac_tipleri, 0.10)
        sk = sum(cr[t]["kapasite"] * n for t, n in spot.items())
        sm = sum(cr[t]["spot_maliyet"] * n for t, n in spot.items())
        return km + sm, kk + sk

    son_tarih = desi["Tarih"].max()
    maliyetler, ihlaller, wpay, wpayda = [], [], 0.0, 0.0
    for h in range(hafta_sayisi):
        tb = son_tarih - pd.Timedelta(days=7 * h); ta = tb - pd.Timedelta(days=6)
        egitim = desi[desi["Tarih"] < ta]
        test = desi[(desi["Tarih"] >= ta) & (desi["Tarih"] <= tb)]
        gd = {ad: g for ad, g in egitim.groupby(["Çıkış Transfer Merkezi", "Varış Transfer Merkezi"])}
        hm = 0.0; hi = 0
        for _, r in test.iterrows():
            rota = (r["Çıkış Transfer Merkezi"], r["Varış Transfer Merkezi"])
            g = gd.get(rota); gercek = r["Toplam Desi"]
            if g is None:
                tah, sap = 0.0, 0.0
            else:
                tah = tahmin_holtwinters(g, r["Tarih"])
                sap = float(np.std(_ayni_gun_son(g, r["Tarih"].dayofweek, son_n_hafta)))
            planlanan = max(tah + k * sap, 0.0)
            maliyet, kapasite = plan_mk(rota, planlanan)
            hm += maliyet
            if kapasite < gercek - 0.01: hi += 1
            wpay += abs(tah - gercek); wpayda += gercek
        maliyetler.append(hm); ihlaller.append(hi)
    return {"ort_maliyet": round(np.mean(maliyetler)), "ort_ihlal": round(np.mean(ihlaller),1),
            "WAPE_%": round(wpay/wpayda*100, 2)}

def rota_adaptif_k(grup, dow, n, k_min, k_max):
    """Rotanin goreli oynakligina (varyasyon katsayisi) gore k secer.
    Sakin rota -> k_min, kaotik rota -> k_max."""
    son = _ayni_gun_son(grup, dow, n)
    if len(son) < 2:
        return (k_min + k_max) / 2
    ort = np.mean(son)
    if ort <= 1:
        return k_max
    cv = np.std(son) / ort   # varyasyon katsayisi
    # cv'yi 0.1-0.6 araligindan k_min-k_max'a esle
    oran = np.clip((cv - 0.1) / (0.6 - 0.1), 0, 1)
    return k_min + oran * (k_max - k_min)

def _ayni_gun_son(grup, dow, n):
    ayni = grup[grup["Tarih"].dt.dayofweek == dow].sort_values("Tarih")
    return ayni.tail(n)["Toplam Desi"].values


def tahmin_kuantil(grup, dow, n=14, q=0.35):
    son = _ayni_gun_son(grup, dow, n)
    if len(son) == 0:
        return grup["Toplam Desi"].median() if len(grup) else 0.0
    return max(np.quantile(son, q), 0.0)


def degerlendir(data, maliyet_df, ayarlar, hafta_sayisi=4, son_n_hafta=14):
    """ayarlar: [(ad, q, k), ...]  q=kuantil dilimi, k=guvenlik payi katsayisi"""
    desi = data["desi"]
    arac_tipleri = list(data["arac"]["Araç Adı"])

    env = defaultdict(int)
    for _, r in data["kiralik"].iterrows():
        env[(r["Çıkış Transfer Merkezi"], r["Varış Transfer Merkezi"], r["Araç Türü"])] += int(r["Araç sayısı"])
    cost_by_rota = defaultdict(dict)
    for _, m in maliyet_df.iterrows():
        cost_by_rota[(m["cikis"], m["varis"])][m["arac_tipi"]] = {
            "kapasite": m["kapasite"], "kiralik_maliyet": m["kiralik_maliyet"], "spot_maliyet": m["spot_maliyet"]
        }

    def plan_maliyet_kapasite(rota, planlanan):
        cost_rota = cost_by_rota.get(rota, {})
        if not cost_rota:
            return 0.0, 0.0
        kir_kap = sum(cost_rota[t]["kapasite"] * env.get((rota[0], rota[1], t), 0) for t in arac_tipleri if t in cost_rota)
        kir_mal = sum(cost_rota[t]["kiralik_maliyet"] * env.get((rota[0], rota[1], t), 0) for t in arac_tipleri if t in cost_rota)
        residual = max(planlanan - kir_kap, 0.0)
        spot = solve_spot(residual, cost_rota, arac_tipleri, 0.10)
        spot_kap = sum(cost_rota[t]["kapasite"] * n for t, n in spot.items())
        spot_mal = sum(cost_rota[t]["spot_maliyet"] * n for t, n in spot.items())
        return kir_mal + spot_mal, kir_kap + spot_kap

    son_tarih = desi["Tarih"].max()
    # Her hafta icin test satirlarini ve sapmayi hazirla
    haftalar = []
    for h in range(hafta_sayisi):
        test_bit = son_tarih - pd.Timedelta(days=7 * h)
        test_bas = test_bit - pd.Timedelta(days=6)
        egitim = desi[desi["Tarih"] < test_bas]
        test = desi[(desi["Tarih"] >= test_bas) & (desi["Tarih"] <= test_bit)]
        gd = {ad: g for ad, g in egitim.groupby(["Çıkış Transfer Merkezi", "Varış Transfer Merkezi"])}
        satir = []
        for _, r in test.iterrows():
            rota = (r["Çıkış Transfer Merkezi"], r["Varış Transfer Merkezi"])
            g = gd.get(rota)
            sap = float(np.std(_ayni_gun_son(g, r["Tarih"].dayofweek, son_n_hafta))) if g is not None else 0.0
            satir.append((rota, g, r["Tarih"].dayofweek, r["Toplam Desi"], sap))
        haftalar.append(satir)

    sonuc = []
    for (ad, q, k) in ayarlar:
        maliyetler, ihlaller, wape_pay, wape_payda = [], [], 0.0, 0.0
        for satir in haftalar:
            hafta_maliyet = 0.0; hafta_ihlal = 0
            for (rota, g, dow, gercek, sap) in satir:
                tah = tahmin_kuantil(g, dow, son_n_hafta, q) if g is not None else 0.0
                planlanan = max(tah + k * sap, 0.0)
                maliyet, kapasite = plan_maliyet_kapasite(rota, planlanan)
                hafta_maliyet += maliyet
                if kapasite < gercek - 0.01:
                    hafta_ihlal += 1
                wape_pay += abs(tah - gercek); wape_payda += gercek
            maliyetler.append(hafta_maliyet); ihlaller.append(hafta_ihlal)
        sonuc.append({
            "ayar": ad,
            "ort_maliyet": round(np.mean(maliyetler)),
            "ort_ihlal": round(np.mean(ihlaller), 1),
            "WAPE_%": round(wape_pay / wape_payda * 100, 2),
        })
    return pd.DataFrame(sonuc)

def degerlendir_adaptif(data, maliyet_df, q, k_aralik_list, hafta_sayisi=4, son_n_hafta=14):
    """k_aralik_list: [(ad, k_min, k_max), ...]  adaptif k araliklari."""
    desi = data["desi"]
    arac_tipleri = list(data["arac"]["Araç Adı"])
    env = defaultdict(int)
    for _, r in data["kiralik"].iterrows():
        env[(r["Çıkış Transfer Merkezi"], r["Varış Transfer Merkezi"], r["Araç Türü"])] += int(r["Araç sayısı"])
    cost_by_rota = defaultdict(dict)
    for _, m in maliyet_df.iterrows():
        cost_by_rota[(m["cikis"], m["varis"])][m["arac_tipi"]] = {
            "kapasite": m["kapasite"], "kiralik_maliyet": m["kiralik_maliyet"], "spot_maliyet": m["spot_maliyet"]
        }

    def plan_mk(rota, planlanan):
        cr = cost_by_rota.get(rota, {})
        if not cr: return 0.0, 0.0
        kk = sum(cr[t]["kapasite"] * env.get((rota[0], rota[1], t), 0) for t in arac_tipleri if t in cr)
        km = sum(cr[t]["kiralik_maliyet"] * env.get((rota[0], rota[1], t), 0) for t in arac_tipleri if t in cr)
        residual = max(planlanan - kk, 0.0)
        spot = solve_spot(residual, cr, arac_tipleri, 0.10)
        sk = sum(cr[t]["kapasite"] * n for t, n in spot.items())
        sm = sum(cr[t]["spot_maliyet"] * n for t, n in spot.items())
        return km + sm, kk + sk

    son_tarih = desi["Tarih"].max()
    haftalar = []
    for h in range(hafta_sayisi):
        tb = son_tarih - pd.Timedelta(days=7 * h)
        ta = tb - pd.Timedelta(days=6)
        egitim = desi[desi["Tarih"] < ta]
        test = desi[(desi["Tarih"] >= ta) & (desi["Tarih"] <= tb)]
        gd = {ad: g for ad, g in egitim.groupby(["Çıkış Transfer Merkezi", "Varış Transfer Merkezi"])}
        satir = []
        for _, r in test.iterrows():
            rota = (r["Çıkış Transfer Merkezi"], r["Varış Transfer Merkezi"])
            satir.append((rota, gd.get(rota), r["Tarih"].dayofweek, r["Toplam Desi"]))
        haftalar.append(satir)

    sonuc = []
    for (ad, k_min, k_max) in k_aralik_list:
        maliyetler, ihlaller = [], []
        for satir in haftalar:
            hm = 0.0; hi = 0
            for (rota, g, dow, gercek) in satir:
                if g is None:
                    tah, sap, kk = 0.0, 0.0, 2.5
                else:
                    son = _ayni_gun_son(g, dow, son_n_hafta)
                    tah = float(np.quantile(son, q)) if len(son) else 0.0
                    sap = float(np.std(son)) if len(son) else 0.0
                    kk = rota_adaptif_k(g, dow, son_n_hafta, k_min, k_max)
                planlanan = max(tah + kk * sap, 0.0)
                maliyet, kapasite = plan_mk(rota, planlanan)
                hm += maliyet
                if kapasite < gercek - 0.01: hi += 1
            maliyetler.append(hm); ihlaller.append(hi)
        sonuc.append({"ayar": ad, "ort_maliyet": round(np.mean(maliyetler)), "ort_ihlal": round(np.mean(ihlaller), 1)})
    return pd.DataFrame(sonuc)

def degerlendir_gun_k(data, maliyet_df, q, gun_k_haritalari, hafta_sayisi=4, son_n_hafta=14):
    """gun_k_haritalari: [(ad, {dow: k}), ...]  her gun icin k sozlugu."""
    desi = data["desi"]
    arac_tipleri = list(data["arac"]["Araç Adı"])
    env = defaultdict(int)
    for _, r in data["kiralik"].iterrows():
        env[(r["Çıkış Transfer Merkezi"], r["Varış Transfer Merkezi"], r["Araç Türü"])] += int(r["Araç sayısı"])
    cost_by_rota = defaultdict(dict)
    for _, m in maliyet_df.iterrows():
        cost_by_rota[(m["cikis"], m["varis"])][m["arac_tipi"]] = {
            "kapasite": m["kapasite"], "kiralik_maliyet": m["kiralik_maliyet"], "spot_maliyet": m["spot_maliyet"]
        }

    def plan_mk(rota, planlanan):
        cr = cost_by_rota.get(rota, {})
        if not cr: return 0.0, 0.0
        kk = sum(cr[t]["kapasite"] * env.get((rota[0], rota[1], t), 0) for t in arac_tipleri if t in cr)
        km = sum(cr[t]["kiralik_maliyet"] * env.get((rota[0], rota[1], t), 0) for t in arac_tipleri if t in cr)
        residual = max(planlanan - kk, 0.0)
        spot = solve_spot(residual, cr, arac_tipleri, 0.10)
        sk = sum(cr[t]["kapasite"] * n for t, n in spot.items())
        sm = sum(cr[t]["spot_maliyet"] * n for t, n in spot.items())
        return km + sm, kk + sk

    son_tarih = desi["Tarih"].max()
    haftalar = []
    for h in range(hafta_sayisi):
        tb = son_tarih - pd.Timedelta(days=7 * h); ta = tb - pd.Timedelta(days=6)
        egitim = desi[desi["Tarih"] < ta]
        test = desi[(desi["Tarih"] >= ta) & (desi["Tarih"] <= tb)]
        gd = {ad: g for ad, g in egitim.groupby(["Çıkış Transfer Merkezi", "Varış Transfer Merkezi"])}
        satir = []
        for _, r in test.iterrows():
            rota = (r["Çıkış Transfer Merkezi"], r["Varış Transfer Merkezi"])
            satir.append((rota, gd.get(rota), r["Tarih"].dayofweek, r["Toplam Desi"]))
        haftalar.append(satir)

    sonuc = []
    for (ad, gun_k) in gun_k_haritalari:
        maliyetler, ihlaller = [], []
        for satir in haftalar:
            hm = 0.0; hi = 0
            for (rota, g, dow, gercek) in satir:
                if g is None:
                    tah, sap = 0.0, 0.0
                else:
                    son = _ayni_gun_son(g, dow, son_n_hafta)
                    tah = float(np.quantile(son, q)) if len(son) else 0.0
                    sap = float(np.std(son)) if len(son) else 0.0
                k = gun_k[dow]
                planlanan = max(tah + k * sap, 0.0)
                maliyet, kapasite = plan_mk(rota, planlanan)
                hm += maliyet
                if kapasite < gercek - 0.01: hi += 1
            maliyetler.append(hm); ihlaller.append(hi)
        sonuc.append({"ayar": ad, "ort_maliyet": round(np.mean(maliyetler)), "ort_ihlal": round(np.mean(ihlaller), 1)})
    return pd.DataFrame(sonuc)

def ihlal_teshis(data, maliyet_df, q=0.35, k=2.5, hafta_sayisi=4, son_n_hafta=14):
    """Hangi rotalar kac kez ihlal ediyor? Ihlaller yogunlasmis mi?"""
    desi = data["desi"]
    arac_tipleri = list(data["arac"]["Araç Adı"])
    env = defaultdict(int)
    for _, r in data["kiralik"].iterrows():
        env[(r["Çıkış Transfer Merkezi"], r["Varış Transfer Merkezi"], r["Araç Türü"])] += int(r["Araç sayısı"])
    cost_by_rota = defaultdict(dict)
    for _, m in maliyet_df.iterrows():
        cost_by_rota[(m["cikis"], m["varis"])][m["arac_tipi"]] = {"kapasite": m["kapasite"]}

    def kapasite(rota, planlanan):
        cr = cost_by_rota.get(rota, {})
        if not cr: return 0.0
        kk = sum(cr[t]["kapasite"] * env.get((rota[0], rota[1], t), 0) for t in arac_tipleri if t in cr)
        residual = max(planlanan - kk, 0.0)
        from optimizer import solve_spot as _ss
        spot = _ss(residual, {t: {"kapasite": cr[t]["kapasite"], "spot_maliyet": 1, "kiralik_maliyet": 1} for t in cr}, arac_tipleri, 0.10)
        return kk + sum(cr[t]["kapasite"] * n for t, n in spot.items())

    son_tarih = desi["Tarih"].max()
    ihlal_sayaci = defaultdict(int)
    for h in range(hafta_sayisi):
        tb = son_tarih - pd.Timedelta(days=7*h); ta = tb - pd.Timedelta(days=6)
        egitim = desi[desi["Tarih"] < ta]
        test = desi[(desi["Tarih"] >= ta) & (desi["Tarih"] <= tb)]
        gd = {ad: g for ad, g in egitim.groupby(["Çıkış Transfer Merkezi", "Varış Transfer Merkezi"])}
        for _, r in test.iterrows():
            rota = (r["Çıkış Transfer Merkezi"], r["Varış Transfer Merkezi"])
            g = gd.get(rota)
            if g is None: continue
            son = _ayni_gun_son(g, r["Tarih"].dayofweek, son_n_hafta)
            tah = float(np.quantile(son, q)) if len(son) else 0.0
            sap = float(np.std(son)) if len(son) else 0.0
            planlanan = max(tah + k*sap, 0.0)
            if kapasite(rota, planlanan) < r["Toplam Desi"] - 0.01:
                ihlal_sayaci[f"{rota[0]}->{rota[1]}"] += 1

    print("=== IHLAL TESHISI (4 hafta, q=0.35 k=2.5) ===")
    toplam = sum(ihlal_sayaci.values())
    print(f"Toplam ihlal (rota-gun): {toplam}")
    print(f"Ihlal eden farkli rota sayisi: {len(ihlal_sayaci)}")
    print("\nEn cok ihlal eden rotalar:")
    for rota, sayi in sorted(ihlal_sayaci.items(), key=lambda x: -x[1])[:12]:
        print(f"  {rota:35s}: {sayi} kez")


if __name__ == "__main__":
    config_yolu = os.path.join(os.path.dirname(__file__), "..", "config.json")
    data = load_all(config_yolu)
    _, maliyet_df = build_costs(data)

    ihlal_teshis(data, maliyet_df)