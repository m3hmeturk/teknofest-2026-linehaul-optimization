"""
Gercekci ugrama simulasyonu (greedy, kapasite kontrollu).
Her gun-cikis icin ugrama firsatli rota ciftlerini, kapasite siniri
icinde birlestirir. Her rota en fazla 1 kez birlesir (cifte sayim yok).
Gercek kazanci TL olarak verir. Hicbir seyi degistirmez.
"""

import os
import pandas as pd
from collections import defaultdict
from data_loader import load_all
from distance_cost import haversine_km, build_all as build_costs
from forecast import build_all as build_forecast
from optimizer import optimize


if __name__ == "__main__":
    config_yolu = os.path.join(os.path.dirname(__file__), "..", "config.json")
    data = load_all(config_yolu)
    koord = data["koordinatlar"].set_index("Transfer Merkezi")[["Enlem", "Boylam"]].to_dict("index")
    arac = data["arac"]
    kap = dict(zip(arac["Araç Adı"], arac["Kapasite (desi)"]))
    spot_sabit = dict(zip(arac["Araç Adı"], arac["Spot Araç Sabit Günlük Maliyet (TL)"]))
    spot_km_m = dict(zip(arac["Araç Adı"], arac["Spot Kilometre Başına Maliyet (TL)"]))
    en_buyuk_kap = max(kap.values())

    def mesafe(a, b):
        return haversine_km(koord[a]["Enlem"], koord[a]["Boylam"], koord[b]["Enlem"], koord[b]["Boylam"])

    mesafe_df, maliyet_df = build_costs(data)
    tahmin_df = build_forecast(data)
    sonuc_df = optimize(data, mesafe_df, maliyet_df, tahmin_df)

    # Ugrama firsatlari (sapma <%15)
    desi = data["desi"]
    rota_set = set(zip(desi["Çıkış Transfer Merkezi"], desi["Varış Transfer Merkezi"]))
    cikis_varis = defaultdict(list)
    for (c, v) in rota_set:
        cikis_varis[c].append(v)
    firsat = {}
    for c, varislar in cikis_varis.items():
        for b in varislar:
            for cc in varislar:
                if b == cc: continue
                dogrudan = mesafe(c, cc)
                if dogrudan < 1: continue
                ekstra = (mesafe(c, b) + mesafe(b, cc)) - dogrudan
                if ekstra / dogrudan < 0.15:
                    firsat[(c, b, cc)] = ekstra

    def en_ucuz_arac(desi_miktar):
        """Bir desi miktarini tasiyabilecek en ucuz (sabit) arac tipi."""
        uygun = [(t, spot_sabit[t]) for t in kap if kap[t] >= desi_miktar]
        if not uygun: return None
        return min(uygun, key=lambda x: x[1])[0]

    toplam_kazanc = 0.0
    birlesme = 0

    for tarih, gun_df in sonuc_df.groupby("tarih"):
        # cikis -> {varis: spot ile tasinan desi}
        cikis_rotalar = defaultdict(dict)
        for _, r in gun_df.iterrows():
            if r["spot_detay"]:
                # spot ile tasinan gercek desi (residual)
                kir_kap = sum(kap[t]*n for t, n in r["kiralik_detay"].items())
                spot_desi = max(r["talep_desi"] - kir_kap, 0)
                cikis_rotalar[r["cikis"]][r["varis"]] = spot_desi

        for c, varis_desi in cikis_rotalar.items():
            birlesmis = set()  # bu gun zaten birlesen varislar
            for (cc_c, b, cc) in list(firsat.keys()):
                if cc_c != c: continue
                if b not in varis_desi or cc not in varis_desi: continue
                if b in birlesmis or cc in birlesmis: continue

                d_b, d_c = varis_desi[b], varis_desi[cc]
                toplam_desi = d_b + d_c
                if toplam_desi > en_buyuk_kap: continue  # tek araca sigmaz

                # Birlestirmeden once: iki ayri arac maliyeti
                a_b = en_ucuz_arac(d_b); a_c = en_ucuz_arac(d_c)
                if a_b is None or a_c is None: continue
                onceki = (spot_sabit[a_b] + spot_km_m[a_b]*mesafe(c, b)
                          + spot_sabit[a_c] + spot_km_m[a_c]*mesafe(c, cc))

                # Birlestikten sonra: tek arac, c->b->cc, toplam_desi tasiyor
                a_yeni = en_ucuz_arac(toplam_desi)
                if a_yeni is None: continue
                sonraki = spot_sabit[a_yeni] + spot_km_m[a_yeni]*(mesafe(c, b)+mesafe(b, cc))

                net = onceki - sonraki
                if net > 0:
                    toplam_kazanc += net
                    birlesme += 1
                    birlesmis.add(b); birlesmis.add(cc)

    spot_toplam = sonuc_df["spot_maliyet"].sum()
    print("=== GERCEKCI UGRAMA SIMULASYONU (greedy, kapasite kontrollu) ===\n")
    print(f"Mevcut spot maliyet : {spot_toplam:,.0f} TL")
    print(f"Gercek birlesme     : {birlesme}")
    print(f"Gercek kazanc       : {toplam_kazanc:,.0f} TL")
    print(f"Spot maliyetin %    : %{toplam_kazanc/spot_toplam*100:.2f}")
    print("\n(Bu greedy bir alt sinir civari; tam MIP biraz daha iyi olabilir)")