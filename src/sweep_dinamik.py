"""
Dinamik guvenlik payi taramasi.
Pay = k * (o rotanin haftanin-ayni-gunundeki standart sapmasi)
Farkli k degerlerini backtest uzerinde dener.
main.py'yi ETKILEMEZ - sadece analiz.
"""

import os
import numpy as np
import pandas as pd
from itertools import product
from collections import defaultdict
from data_loader import load_all
from distance_cost import build_all as build_costs


def tahmin_ve_sapma(grup, hedef_gun, son_n_hafta=6):
    """Ayni gunun son N haftasinin agirlikli ortalamasi VE standart sapmasi."""
    ayni_gun = grup[grup["Tarih"].dt.dayofweek == hedef_gun].sort_values("Tarih")
    if len(ayni_gun) == 0:
        ort = grup["Toplam Desi"].mean() if len(grup) else 0.0
        sap = grup["Toplam Desi"].std() if len(grup) > 1 else 0.0
        return float(ort), float(sap if not np.isnan(sap) else 0.0)
    son = ayni_gun.tail(son_n_hafta)["Toplam Desi"].values
    agirlik = np.arange(1, len(son) + 1)
    ort = float(np.average(son, weights=agirlik))
    sap = float(np.std(son)) if len(son) > 1 else 0.0
    return ort, sap


def en_ucuz_plan(talep, tipler):
    best = None
    for combo in product(range(0, 7), repeat=len(tipler)):
        cap = sum(c * tipler[i][1] for i, c in enumerate(combo))
        if cap < talep:
            continue
        cost = sum(c * tipler[i][2] for i, c in enumerate(combo))
        if best is None or cost < best[0]:
            best = (cost, cap)
    return best


def degerlendir(desi, maliyet_df, k_degerleri, test_gun=7, son_n_hafta=6):
    son_tarih = desi["Tarih"].max()
    test_baslangic = son_tarih - pd.Timedelta(days=test_gun - 1)
    egitim = desi[desi["Tarih"] < test_baslangic].copy()
    test = desi[desi["Tarih"] >= test_baslangic].copy()

    grup_dict = {ad: g for ad, g in egitim.groupby(["Çıkış Transfer Merkezi", "Varış Transfer Merkezi"])}

    cost_lk = defaultdict(list)
    for _, m in maliyet_df.iterrows():
        cost_lk[(m["cikis"], m["varis"])].append((m["arac_tipi"], m["kapasite"], m["spot_maliyet"]))

    # Her test satiri icin ortalama + sapma + gercek
    satirlar = []
    for _, r in test.iterrows():
        rota = (r["Çıkış Transfer Merkezi"], r["Varış Transfer Merkezi"])
        grup = grup_dict.get(rota)
        if grup is not None:
            ort, sap = tahmin_ve_sapma(grup, r["Tarih"].dayofweek, son_n_hafta)
        else:
            ort, sap = 0.0, 0.0
        satirlar.append((rota, ort, sap, r["Toplam Desi"]))

    sonuc = []
    for k in k_degerleri:
        toplam_maliyet = 0.0
        ihlal = 0
        ihlal_desi = 0.0
        for (rota, ort, sap, gercek) in satirlar:
            tipler = cost_lk.get(rota)
            if not tipler:
                continue
            planlanan = max(ort + k * sap, 0.0)
            plan = en_ucuz_plan(planlanan, tipler)
            if plan is None:
                continue
            maliyet, kapasite = plan
            toplam_maliyet += maliyet
            if kapasite < gercek:
                ihlal += 1
                ihlal_desi += (gercek - kapasite)
        sonuc.append({
            "k": k,
            "ihlal_satir": ihlal,
            "ihlal_%": round(ihlal / len(satirlar) * 100, 1),
            "ihlal_desi": round(ihlal_desi),
            "toplam_maliyet": round(toplam_maliyet),
        })
    return pd.DataFrame(sonuc)


if __name__ == "__main__":
    config_yolu = os.path.join(os.path.dirname(__file__), "..", "config.json")
    data = load_all(config_yolu)
    _, maliyet_df = build_costs(data)

    k_degerleri = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
    tablo = degerlendir(data["desi"], maliyet_df, k_degerleri)

    print("=== DINAMIK PAY TARAMASI (Pay = k * sapma) ===")
    print("(spot-only varsayimi; paylar arasi karsilastirma icin)\n")
    print(tablo.to_string(index=False))

    print("\n--- Karsilastirma: sabit %pay en iyi neydi? ---")
    print("Sabit %40 pay: 64 ihlal, maliyet ~16,764,191")
    print("Sabit %80 pay: 23 ihlal, maliyet ~19,622,870")