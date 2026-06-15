"""
Guvenlik payi taramasi (sweep).
Farkli pay seviyelerini backtest uzerinde dener:
- Ihlal orani: gercek talep > atanan kapasite olan satirlar
- Toplam maliyet
Amac: ihlali dusuren en ucuz payi bulmak. main.py'yi ETKILEMEZ.
"""

import os
import numpy as np
import pandas as pd
from collections import defaultdict
from data_loader import load_all
from distance_cost import build_all as build_costs


def _hafta_gunu_ortalama(grup, hedef_gun, son_n_hafta=6):
    ayni_gun = grup[grup["Tarih"].dt.dayofweek == hedef_gun].sort_values("Tarih")
    if len(ayni_gun) == 0:
        return grup["Toplam Desi"].mean() if len(grup) else 0.0
    son = ayni_gun.tail(son_n_hafta)["Toplam Desi"].values
    agirlik = np.arange(1, len(son) + 1)
    return float(np.average(son, weights=agirlik))


def en_ucuz_plan(talep, gd, tipler):
    """Bir talebi karsilayan en ucuz arac kombinasyonunu (greedy degil, kucuk
    brute-force) bulur. tipler: [(ad, kapasite, spot_maliyet), ...] sirali."""
    from itertools import product
    best = None
    for combo in product(range(0, 7), repeat=len(tipler)):
        cap = sum(c * tipler[i][1] for i, c in enumerate(combo))
        if cap < talep:
            continue
        cost = sum(c * tipler[i][2] for i, c in enumerate(combo))
        if best is None or cost < best[0]:
            best = (cost, cap)
    return best  # (maliyet, kapasite)


def degerlendir(desi, maliyet_df, arac, paylar, test_gun=7, son_n_hafta=6):
    son_tarih = desi["Tarih"].max()
    test_baslangic = son_tarih - pd.Timedelta(days=test_gun - 1)
    egitim = desi[desi["Tarih"] < test_baslangic].copy()
    test = desi[desi["Tarih"] >= test_baslangic].copy()

    grup_dict = {ad: g for ad, g in egitim.groupby(["Çıkış Transfer Merkezi", "Varış Transfer Merkezi"])}

    # Maliyet lookup: (cikis,varis) -> sirali tip listesi [(ad,kap,spot_maliyet)]
    cost_lk = defaultdict(list)
    for _, m in maliyet_df.iterrows():
        cost_lk[(m["cikis"], m["varis"])].append((m["arac_tipi"], m["kapasite"], m["spot_maliyet"]))

    # Once her test satiri icin tahmini hesapla (pay'dan bagimsiz)
    satirlar = []
    for _, r in test.iterrows():
        rota = (r["Çıkış Transfer Merkezi"], r["Varış Transfer Merkezi"])
        grup = grup_dict.get(rota)
        tahmin = _hafta_gunu_ortalama(grup, r["Tarih"].dayofweek, son_n_hafta) if grup is not None else 0.0
        satirlar.append((rota, max(tahmin, 0.0), r["Toplam Desi"]))

    sonuc = []
    for pay in paylar:
        toplam_maliyet = 0.0
        ihlal = 0
        ihlal_desi = 0.0
        for (rota, tahmin, gercek) in satirlar:
            tipler = cost_lk.get(rota)
            if not tipler:
                continue
            planlanan_talep = tahmin * (1 + pay)
            plan = en_ucuz_plan(planlanan_talep, None, tipler)
            if plan is None:
                # cok buyuk talep - en buyuk araclarla doldur (nadir)
                continue
            maliyet, kapasite = plan
            toplam_maliyet += maliyet
            if kapasite < gercek:  # GERCEK talep karsilanamadi
                ihlal += 1
                ihlal_desi += (gercek - kapasite)
        sonuc.append({
            "pay_%": round(pay * 100, 1),
            "ihlal_satir": ihlal,
            "ihlal_desi": round(ihlal_desi),
            "toplam_maliyet": round(toplam_maliyet),
        })
    return pd.DataFrame(sonuc)


if __name__ == "__main__":
    config_yolu = os.path.join(os.path.dirname(__file__), "..", "config.json")
    data = load_all(config_yolu)
    _, maliyet_df = build_costs(data)

    paylar = [0.0, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80]
    tablo = degerlendir(data["desi"], maliyet_df, data["arac"], paylar)

    print("=== GUVENLIK PAYI TARAMASI (test: son 7 gun) ===")
    print("(spot-only varsayimi ile; gercek modelde kiralik daha da ucuzlatir)\n")
    print(tablo.to_string(index=False))

    # En ucuz, ihlal_satir == 0 olan pay
    sifir_ihlal = tablo[tablo["ihlal_satir"] == 0]
    if len(sifir_ihlal):
        en_iyi = sifir_ihlal.nsmallest(1, "toplam_maliyet").iloc[0]
        print(f"\n>>> Sifir ihlal saglayan en ucuz pay: %{en_iyi['pay_%']} "
              f"(maliyet {en_iyi['toplam_maliyet']:,.0f})")
    else:
        print("\n>>> Hicbir pay sifir ihlal saglamadi - daha yuksek pay denenebilir.")