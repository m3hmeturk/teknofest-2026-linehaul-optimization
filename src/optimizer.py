"""
Katman 4 - OR-Tools MIP Optimizasyonu
-------------------------------------
Her gun icin ayri MIP. Dataset A: konsolidasyon kapali, dogrudan rota.
- Kiralik: rotaya sabit, gunluk kira BATIK (amaca girmez), sadece km.
- Spot: sinirsiz, sabit + km.
- Kisit: kapasite >= talep, kiralik <= mevcut envanter.
- Amac: toplam optimizasyon maliyetini minimize et.
"""

import os
import pandas as pd
from collections import defaultdict
from ortools.linear_solver import pywraplp


def _kiralik_envanteri(kiralik):
    """ (cikis, varis, arac_tipi) -> mevcut kiralik adedi """
    env = defaultdict(int)
    for _, r in kiralik.iterrows():
        env[(r["Çıkış Transfer Merkezi"], r["Varış Transfer Merkezi"], r["Araç Türü"])] += int(r["Araç sayısı"])
    return env


def _maliyet_lookup(maliyet_df):
    """ (cikis, varis, arac_tipi) -> maliyet bilgisi sozlugu """
    lk = {}
    for _, m in maliyet_df.iterrows():
        lk[(m["cikis"], m["varis"], m["arac_tipi"])] = {
            "kapasite": m["kapasite"],
            "kiralik_opt": m["kiralik_opt_maliyet"],
            "kiralik_tam": m["kiralik_tam_maliyet"],
            "kiralik_kira": m["kiralik_gunluk_kira"],
            "spot": m["spot_maliyet"],
        }
    return lk


def solve_gun(gun_talep, env, maliyet_lk, arac_tipleri):
    """Tek bir gunun MIP'ini cozer. gun_talep: [(cikis,varis,desi), ...]"""
    solver = pywraplp.Solver.CreateSolver("CBC")
    if solver is None:
        raise RuntimeError("CBC solver bulunamadi.")

    x = {}  # kiralik degiskenleri
    y = {}  # spot degiskenleri
    amac = solver.Objective()

    for (cikis, varis, desi) in gun_talep:
        kapasite_terimleri = []
        for tip in arac_tipleri:
            anahtar = (cikis, varis, tip)
            bilgi = maliyet_lk.get(anahtar)
            if bilgi is None:
                continue
            kap = bilgi["kapasite"]

            # Spot degiskeni (her rota-tip icin var, ust sinir yok)
            yv = solver.IntVar(0, solver.infinity(), f"y_{cikis}_{varis}_{tip}")
            y[(cikis, varis, tip)] = yv
            amac.SetCoefficient(yv, float(bilgi["spot"]))
            kapasite_terimleri.append(kap * yv)

            # Kiralik degiskeni (sadece envanterde varsa)
            mevcut = env.get(anahtar, 0)
            if mevcut > 0:
                xv = solver.IntVar(0, mevcut, f"x_{cikis}_{varis}_{tip}")
                x[(cikis, varis, tip)] = xv
                amac.SetCoefficient(xv, float(bilgi["kiralik_opt"]))
                kapasite_terimleri.append(kap * xv)

        # Talep kisiti: toplam kapasite >= talep
        if kapasite_terimleri:
            solver.Add(sum(kapasite_terimleri) >= desi)

    amac.SetMinimization()
    durum = solver.Solve()
    if durum not in (pywraplp.Solver.OPTIMAL, pywraplp.Solver.FEASIBLE):
        raise RuntimeError(f"Cozum bulunamadi (durum={durum})")

    # Sonuclari topla
    sonuc = []
    for (cikis, varis, desi) in gun_talep:
        kiralik_adetleri = {}
        spot_adetleri = {}
        for tip in arac_tipleri:
            xv = x.get((cikis, varis, tip))
            yv = y.get((cikis, varis, tip))
            ka = int(round(xv.solution_value())) if xv is not None else 0
            sa = int(round(yv.solution_value())) if yv is not None else 0
            if ka > 0:
                kiralik_adetleri[tip] = ka
            if sa > 0:
                spot_adetleri[tip] = sa
        sonuc.append((cikis, varis, desi, kiralik_adetleri, spot_adetleri))
    return sonuc


def optimize(data, mesafe_df, maliyet_df, tahmin_df):
    arac_tipleri = list(data["arac"]["Araç Adı"])
    env = _kiralik_envanteri(data["kiralik"])
    maliyet_lk = _maliyet_lookup(maliyet_df)

    tum_sonuclar = []
    for tarih, gun_df in tahmin_df.groupby("tarih"):
        gun_talep = [(r["cikis"], r["varis"], r["tahmin_desi"]) for _, r in gun_df.iterrows()]
        gun_sonuc = solve_gun(gun_talep, env, maliyet_lk, arac_tipleri)

        for (cikis, varis, desi, kir, spot) in gun_sonuc:
            # Maliyet kirilimi hesapla
            kiralik_tam = sum(maliyet_lk[(cikis, varis, t)]["kiralik_tam"] * n for t, n in kir.items())
            kiralik_opt = sum(maliyet_lk[(cikis, varis, t)]["kiralik_opt"] * n for t, n in kir.items())
            spot_maliyet = sum(maliyet_lk[(cikis, varis, t)]["spot"] * n for t, n in spot.items())
            kapasite = (sum(maliyet_lk[(cikis, varis, t)]["kapasite"] * n for t, n in kir.items())
                        + sum(maliyet_lk[(cikis, varis, t)]["kapasite"] * n for t, n in spot.items()))

            tum_sonuclar.append({
                "tarih": tarih,
                "cikis": cikis,
                "varis": varis,
                "talep_desi": desi,
                "atanan_kapasite": kapasite,
                "kiralik_detay": kir,
                "spot_detay": spot,
                "kiralik_tam_maliyet": round(kiralik_tam, 2),
                "kiralik_opt_maliyet": round(kiralik_opt, 2),
                "spot_maliyet": round(spot_maliyet, 2),
            })
    return pd.DataFrame(tum_sonuclar)


if __name__ == "__main__":
    from data_loader import load_all
    from distance_cost import build_all as build_costs
    from forecast import build_all as build_forecast

    config_yolu = os.path.join(os.path.dirname(__file__), "..", "config.json")
    data = load_all(config_yolu)
    mesafe_df, maliyet_df = build_costs(data)
    tahmin_df = build_forecast(data)

    sonuc_df = optimize(data, mesafe_df, maliyet_df, tahmin_df)

    print("=== OPTIMIZASYON SONUCU ===")
    print(f"Toplam plan satiri: {len(sonuc_df)}")

    spot_toplam = sonuc_df["spot_maliyet"].sum()
    kiralik_km_toplam = sonuc_df["kiralik_opt_maliyet"].sum()
    kiralik_tam_toplam = sonuc_df["kiralik_tam_maliyet"].sum()

    print(f"\n--- HAFTALIK MALIYET KIRILIMI ---")
    print(f"Spot maliyeti (baseline metrigi): {spot_toplam:,.2f} TL")
    print(f"Kiralik km maliyeti            : {kiralik_km_toplam:,.2f} TL")
    print(f"Kiralik tam maliyet (kira dahil): {kiralik_tam_toplam:,.2f} TL")
    print(f"TOPLAM (spot + kiralik tam)     : {spot_toplam + kiralik_tam_toplam:,.2f} TL")

    # Kontrol: talep her zaman karsilandi mi?
    eksik = sonuc_df[sonuc_df["atanan_kapasite"] < sonuc_df["talep_desi"] - 0.01]
    print(f"\nTalebi karsilamayan rota sayisi: {len(eksik)} (0 olmali)")

    print("\nOrnek (kiralik kullanilan ilk 5 satir):")
    ornek = sonuc_df[sonuc_df["kiralik_detay"] != {}].head(5)
    for _, r in ornek.iterrows():
        print(f"  {r['tarih']} {r['cikis']}->{r['varis']} | talep={r['talep_desi']:.0f} "
              f"| kiralik={r['kiralik_detay']} | spot={r['spot_detay']}")