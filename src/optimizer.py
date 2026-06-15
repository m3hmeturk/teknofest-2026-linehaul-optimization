"""
Katman 4 - OR-Tools MIP Optimizasyonu (YENI KURALLAR)
-----------------------------------------------------
- Kiralik ZORUNLU + oncelikli: o rotadaki tum kiralik araclar her gun cikar.
- Residual talep (kiralik sonrasi) spot ile karsilanir.
- Minimum %10 spot doluluk: spot kapasitesi <= 10 * residual.
- Mesafe tek yon. Kiralik maliyet = kira + km (toplama dahil).
- Cikti: arac basina atanan desi + maliyet.
"""

import os
import pandas as pd
from collections import defaultdict
from ortools.linear_solver import pywraplp


def _kiralik_envanteri(kiralik):
    env = defaultdict(int)
    for _, r in kiralik.iterrows():
        env[(r["Çıkış Transfer Merkezi"], r["Varış Transfer Merkezi"], r["Araç Türü"])] += int(r["Araç sayısı"])
    return env


def _maliyet_lookup(maliyet_df):
    lk = {}
    for _, m in maliyet_df.iterrows():
        lk[(m["cikis"], m["varis"], m["arac_tipi"])] = {
            "kapasite": m["kapasite"],
            "kiralik_maliyet": m["kiralik_maliyet"],
            "spot_maliyet": m["spot_maliyet"],
        }
    return lk


def _en_kucuk_kapasite(arac):
    return min(arac["Kapasite (desi)"])


def solve_spot(residual, cost_lk_rota, arac_tipleri, min_doluluk=0.10):
    """Residual talebi en ucuz spot kombinasyonuyla karsilar.
    Kisit: residual <= toplam_kapasite <= residual / min_doluluk.
    Doner: {arac_tipi: adet}"""
    if residual <= 0:
        return {}

    solver = pywraplp.Solver.CreateSolver("CBC")
    y = {}
    amac = solver.Objective()
    kapasite_terimleri = []

    for tip in arac_tipleri:
        bilgi = cost_lk_rota.get(tip)
        if bilgi is None:
            continue
        yv = solver.IntVar(0, solver.infinity(), f"y_{tip}")
        y[tip] = yv
        amac.SetCoefficient(yv, float(bilgi["spot_maliyet"]))
        kapasite_terimleri.append(bilgi["kapasite"] * yv)

    # Talep kisiti: kapasite >= residual
    solver.Add(sum(kapasite_terimleri) >= residual)
    # Min %10 doluluk: kapasite <= residual / 0.10  (= 10 * residual)
    ust_sinir = residual / min_doluluk
    solver.Add(sum(kapasite_terimleri) <= ust_sinir)

    amac.SetMinimization()
    durum = solver.Solve()

    if durum not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
        # %10 kisiti saglanamadi (residual cok kucuk) -> en kucuk araci ata
        en_ucuz_tip = min(
            (t for t in arac_tipleri if t in cost_lk_rota),
            key=lambda t: cost_lk_rota[t]["spot_maliyet"]
        )
        # residual'i karsilayacak en kucuk kapasiteli tek arac
        uygunlar = [(t, cost_lk_rota[t]["kapasite"]) for t in arac_tipleri if t in cost_lk_rota]
        uygunlar.sort(key=lambda x: x[1])
        for t, kap in uygunlar:
            if kap >= residual:
                return {t: 1}
        return {uygunlar[-1][0]: 1}  # en buyuk bile yetmezse (olmamali)

    return {tip: int(round(v.solution_value())) for tip, v in y.items() if v.solution_value() > 0.5}


def optimize(data, mesafe_df, maliyet_df, tahmin_df):
    arac_tipleri = list(data["arac"]["Araç Adı"])
    env = _kiralik_envanteri(data["kiralik"])
    maliyet_lk = _maliyet_lookup(maliyet_df)
    min_doluluk = 0.10

    # Maliyet lookup'i rota bazinda grupla
    cost_by_rota = defaultdict(dict)
    for (c, v, t), bilgi in maliyet_lk.items():
        cost_by_rota[(c, v)][t] = bilgi

    sonuclar = []
    for _, r in tahmin_df.iterrows():
        cikis, varis, talep = r["cikis"], r["varis"], r["tahmin_desi"]
        tarih = r["tarih"]
        cost_rota = cost_by_rota.get((cikis, varis), {})

        # 1) Kiralik araclari belirle (o rotada tanimli tum kiralik -> zorunlu)
        kiralik_adet = {}
        kiralik_kapasite = 0
        for tip in arac_tipleri:
            adet = env.get((cikis, varis, tip), 0)
            if adet > 0:
                kiralik_adet[tip] = adet
                kiralik_kapasite += cost_rota[tip]["kapasite"] * adet

        # 2) Residual = talep - kiralik kapasite
        residual = max(talep - kiralik_kapasite, 0.0)

        # 3) Spot cozumu
        spot_adet = solve_spot(residual, cost_rota, arac_tipleri, min_doluluk)

        # 4) Maliyetler
        kiralik_maliyet = sum(cost_rota[t]["kiralik_maliyet"] * n for t, n in kiralik_adet.items())
        spot_maliyet = sum(cost_rota[t]["spot_maliyet"] * n for t, n in spot_adet.items())
        atanan_kapasite = (kiralik_kapasite
                           + sum(cost_rota[t]["kapasite"] * n for t, n in spot_adet.items()))

        sonuclar.append({
            "tarih": tarih,
            "cikis": cikis,
            "varis": varis,
            "talep_desi": talep,
            "atanan_kapasite": atanan_kapasite,
            "kiralik_detay": kiralik_adet,
            "spot_detay": spot_adet,
            "kiralik_maliyet": round(kiralik_maliyet, 2),
            "spot_maliyet": round(spot_maliyet, 2),
        })
    return pd.DataFrame(sonuclar)


if __name__ == "__main__":
    from data_loader import load_all
    from distance_cost import build_all as build_costs
    from forecast import build_all as build_forecast

    config_yolu = os.path.join(os.path.dirname(__file__), "..", "config.json")
    data = load_all(config_yolu)
    mesafe_df, maliyet_df = build_costs(data)
    tahmin_df = build_forecast(data)

    sonuc_df = optimize(data, mesafe_df, maliyet_df, tahmin_df)

    print("=== OPTIMIZASYON SONUCU (yeni kurallar) ===")
    print(f"Toplam plan satiri: {len(sonuc_df)}")

    spot_toplam = sonuc_df["spot_maliyet"].sum()
    kiralik_toplam = sonuc_df["kiralik_maliyet"].sum()
    print(f"\n--- HAFTALIK MALIYET ---")
    print(f"Spot maliyeti    : {spot_toplam:,.2f} TL")
    print(f"Kiralik maliyeti : {kiralik_toplam:,.2f} TL")
    print(f"TOPLAM           : {spot_toplam + kiralik_toplam:,.2f} TL")

    # Kontrol: talep karsilandi mi (kendi tahminimize gore)
    eksik = sonuc_df[sonuc_df["atanan_kapasite"] < sonuc_df["talep_desi"] - 0.01]
    print(f"\nTalebi karsilamayan satir: {len(eksik)} (0 olmali)")

    # Kontrol: min %10 doluluk (spot)
    arac_kap = dict(zip(data["arac"]["Araç Adı"], data["arac"]["Kapasite (desi)"]))
    ihlal_10 = 0
    for _, r in sonuc_df.iterrows():
        if not r["spot_detay"]:
            continue
        residual = max(r["talep_desi"] - sum(arac_kap[t]*n for t,n in r["kiralik_detay"].items()), 0)
        spot_kap = sum(arac_kap[t]*n for t,n in r["spot_detay"].items())
        if spot_kap > 0 and residual > 560 and spot_kap > residual/0.10 + 1:
            ihlal_10 += 1
    print(f"Min %10 doluluk ihlali (residual>560 olanlarda): {ihlal_10} (0 olmali)")