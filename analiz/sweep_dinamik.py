"""
Dinamik guvenlik payi taramasi - YENI KURALLAR.
Pay = k * (rotanin haftanin-ayni-gunundeki standart sapmasi)
Her k icin:
  - tahmin_maliyet: bizim tahminimiz uzerinden plan maliyeti (raporlanan)
  - ihlal: gercek talebe karsi karsilanamayan satir sayisi
Tek yon mesafe + %10 spot kurali + kiralik zorunlu dahil.
main.py'yi ETKILEMEZ.
"""

import os
import numpy as np
import pandas as pd
from collections import defaultdict
from data_loader import load_all
from distance_cost import build_all as build_costs
from optimizer import solve_spot


def tahmin_ve_sapma(grup, hedef_gun, son_n_hafta=6):
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


def degerlendir(data, maliyet_df, k_degerleri, test_gun=7, son_n_hafta=6):
    desi = data["desi"]
    arac_tipleri = list(data["arac"]["Araç Adı"])
    arac_kap = dict(zip(data["arac"]["Araç Adı"], data["arac"]["Kapasite (desi)"]))

    # kiralik envanteri ve maliyet lookup
    env = defaultdict(int)
    for _, r in data["kiralik"].iterrows():
        env[(r["Çıkış Transfer Merkezi"], r["Varış Transfer Merkezi"], r["Araç Türü"])] += int(r["Araç sayısı"])
    cost_by_rota = defaultdict(dict)
    for _, m in maliyet_df.iterrows():
        cost_by_rota[(m["cikis"], m["varis"])][m["arac_tipi"]] = {
            "kapasite": m["kapasite"], "kiralik_maliyet": m["kiralik_maliyet"], "spot_maliyet": m["spot_maliyet"]
        }

    son_tarih = desi["Tarih"].max()
    test_baslangic = son_tarih - pd.Timedelta(days=test_gun - 1)
    egitim = desi[desi["Tarih"] < test_baslangic].copy()
    test = desi[desi["Tarih"] >= test_baslangic].copy()
    grup_dict = {ad: g for ad, g in egitim.groupby(["Çıkış Transfer Merkezi", "Varış Transfer Merkezi"])}

    # Her test satiri: rota, ortalama, sapma, gercek talep
    satirlar = []
    for _, r in test.iterrows():
        rota = (r["Çıkış Transfer Merkezi"], r["Varış Transfer Merkezi"])
        grup = grup_dict.get(rota)
        if grup is not None:
            ort, sap = tahmin_ve_sapma(grup, r["Tarih"].dayofweek, son_n_hafta)
        else:
            ort, sap = 0.0, 0.0
        satirlar.append((rota, ort, sap, r["Toplam Desi"]))

    def plan_kapasite_maliyet(rota, planlanan):
        """Bir rota icin kiralik(zorunlu)+spot plani; (kapasite, maliyet) doner."""
        cost_rota = cost_by_rota.get(rota, {})
        if not cost_rota:
            return 0.0, 0.0
        kir_kap = sum(cost_rota[t]["kapasite"] * env.get((rota[0], rota[1], t), 0)
                      for t in arac_tipleri if t in cost_rota)
        kir_mal = sum(cost_rota[t]["kiralik_maliyet"] * env.get((rota[0], rota[1], t), 0)
                      for t in arac_tipleri if t in cost_rota)
        residual = max(planlanan - kir_kap, 0.0)
        spot = solve_spot(residual, cost_rota, arac_tipleri, 0.10)
        spot_kap = sum(cost_rota[t]["kapasite"] * n for t, n in spot.items())
        spot_mal = sum(cost_rota[t]["spot_maliyet"] * n for t, n in spot.items())
        return kir_kap + spot_kap, kir_mal + spot_mal

    sonuc = []
    for k in k_degerleri:
        toplam_maliyet = 0.0
        ihlal = 0
        for (rota, ort, sap, gercek) in satirlar:
            planlanan = max(ort + k * sap, 0.0)
            kapasite, maliyet = plan_kapasite_maliyet(rota, planlanan)
            toplam_maliyet += maliyet
            if kapasite < gercek - 0.01:   # gercek talep karsilanamadi
                ihlal += 1
        sonuc.append({
            "k": k,
            "ihlal_satir": ihlal,
            "ihlal_%": round(ihlal / len(satirlar) * 100, 1),
            "tahmin_maliyet": round(toplam_maliyet),
        })
    return pd.DataFrame(sonuc)


if __name__ == "__main__":
    config_yolu = os.path.join(os.path.dirname(__file__), "..", "config.json")
    data = load_all(config_yolu)
    _, maliyet_df = build_costs(data)

    k_degerleri = [0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
    tablo = degerlendir(data, maliyet_df, k_degerleri)

    print("=== DINAMIK PAY TARAMASI (YENI KURALLAR, test: son 7 gun) ===")
    print("tahmin_maliyet = bizim tahminimiz uzerinden plan maliyeti (raporlanan)")
    print("ihlal = plan gercek talebi karsilayamayan satir\n")
    print(tablo.to_string(index=False))