"""
Ugrama kazanc tahmini.
Mevcut plan ciktisini kullanarak, ayni gun-ayni cikis-ugrama firsatli
rota ciftlerinde birlestirilebilecek SPOT araclari bulur, kabaca kazanci olcer.
Hicbir seyi degistirmez.
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
    spot_km = dict(zip(arac["Araç Adı"], arac["Spot Kilometre Başına Maliyet (TL)"]))

    def mesafe(a, b):
        return haversine_km(koord[a]["Enlem"], koord[a]["Boylam"], koord[b]["Enlem"], koord[b]["Boylam"])

    # Planimizi uret
    mesafe_df, maliyet_df = build_costs(data)
    tahmin_df = build_forecast(data)
    sonuc_df = optimize(data, mesafe_df, maliyet_df, tahmin_df)

    # Ugrama firsatlari (sapma <%15, daha muhafazakar)
    desi = data["desi"]
    rota_set = set(zip(desi["Çıkış Transfer Merkezi"], desi["Varış Transfer Merkezi"]))
    cikis_varis = defaultdict(list)
    for (c, v) in rota_set:
        cikis_varis[c].append(v)

    firsat = {}  # (cikis, varis_b, varis_c) -> ekstra_km
    for c, varislar in cikis_varis.items():
        for b in varislar:
            for cc in varislar:
                if b == cc: continue
                dogrudan = mesafe(c, cc)
                if dogrudan < 1: continue
                ekstra = (mesafe(c, b) + mesafe(b, cc)) - dogrudan
                if ekstra / dogrudan < 0.15:
                    firsat[(c, b, cc)] = ekstra

    # Her gun-cikis icin, spot araclari topla ve birlestirme dene
    toplam_kazanc = 0.0
    birlesme_sayisi = 0

    # sonuc_df'te spot_detay var; her satirin spot araclarini cikar
    for tarih, gun_df in sonuc_df.groupby("tarih"):
        # cikis -> [(varis, residual_spot_desi, spot_detay)]
        cikis_gruplar = defaultdict(list)
        for _, r in gun_df.iterrows():
            if r["spot_detay"]:
                # bu rotada spot ile tasinan toplam desi (residual)
                spot_kap_toplam = sum(kap[t]*n for t, n in r["spot_detay"].items())
                cikis_gruplar[r["cikis"]].append({
                    "varis": r["varis"], "spot_detay": dict(r["spot_detay"]),
                    "spot_kap": spot_kap_toplam, "talep": r["talep_desi"]
                })

        # Ayni cikistan, ugrama firsatli ciftleri ara
        for c, rotalar in cikis_gruplar.items():
            for i in range(len(rotalar)):
                for j in range(len(rotalar)):
                    if i == j: continue
                    rb, rc = rotalar[i], rotalar[j]
                    b, cc = rb["varis"], rc["varis"]
                    if (c, b, cc) not in firsat: continue
                    # rc'nin spotu, rb'nin aracinda bos yere sigar mi?
                    # En kucuk spot araci (Kamyonet) kazanci icin yeterli mi bak
                    # Basit kazanc: rc'nin en ucuz spot aracini iptal et, ekstra km ekle
                    if not rc["spot_detay"]: continue
                    en_ucuz_tip = min(rc["spot_detay"], key=lambda t: spot_sabit[t])
                    kurtarilan = spot_sabit[en_ucuz_tip]  # sabit maliyet kurtulur
                    ekstra_km_maliyet = spot_km[en_ucuz_tip] * firsat[(c, b, cc)]
                    net = kurtarilan - ekstra_km_maliyet
                    if net > 0:
                        toplam_kazanc += net
                        birlesme_sayisi += 1
                        break  # bu rotayi bir kez birlestir

    spot_toplam = sonuc_df["spot_maliyet"].sum()
    print("=== UGRAMA KAZANC TAHMINI (kaba ust sinir) ===\n")
    print(f"Mevcut spot maliyet      : {spot_toplam:,.0f} TL")
    print(f"Potansiyel birlesme      : {birlesme_sayisi}")
    print(f"Tahmini kazanc (ust sinir): {toplam_kazanc:,.0f} TL")
    print(f"Spot maliyetin yuzdesi   : %{toplam_kazanc/spot_toplam*100:.2f}")
    print("\n(Not: bu KABA bir ust sinir; gercek kazanc kapasite kisitlari nedeniyle daha dusuk olur)")