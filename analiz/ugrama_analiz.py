"""
Ugrama fizibilite analizi.
Ayni cikistan giden rotalarda, A->B->C nin A->C'ye gore sapmasini olcer.
Sapma kucukse ugrama mantikli. Hicbir seyi degistirmez, sadece analiz.
"""

import os
from data_loader import load_all
from distance_cost import haversine_km
import pandas as pd
from collections import defaultdict


if __name__ == "__main__":
    config_yolu = os.path.join(os.path.dirname(__file__), "..", "config.json")
    data = load_all(config_yolu)
    koord = data["koordinatlar"].set_index("Transfer Merkezi")[["Enlem","Boylam"]].to_dict("index")

    def mesafe(a, b):
        return haversine_km(koord[a]["Enlem"], koord[a]["Boylam"], koord[b]["Enlem"], koord[b]["Boylam"])

    # Talep rotalari
    desi = data["desi"]
    rotalar = desi.groupby(["Çıkış Transfer Merkezi","Varış Transfer Merkezi"]).size().reset_index()
    rota_set = set(zip(rotalar["Çıkış Transfer Merkezi"], rotalar["Varış Transfer Merkezi"]))

    # Ayni cikistan giden varislari grupla
    cikis_varis = defaultdict(list)
    for (c, v) in rota_set:
        cikis_varis[c].append(v)

    # Her cikis icin: A->B->C, A->C'ye gore ne kadar sapma yaratiyor?
    # Ugrama mantikli ise: A->B + B->C ~ A->C (B yol uzerinde)
    firsatlar = []
    for c, varislar in cikis_varis.items():
        for b in varislar:
            for cc in varislar:
                if b == cc: continue
                # A->C dogrudan vs A->B->C
                dogrudan = mesafe(c, cc)
                ugrayarak = mesafe(c, b) + mesafe(b, cc)
                if dogrudan < 1: continue
                sapma_orani = (ugrayarak - dogrudan) / dogrudan
                # B, A-C yolunun uzerindeyse sapma kucuk olur
                if sapma_orani < 0.30:  # %30'dan az sapma = yol uzerinde sayilir
                    firsatlar.append({
                        "cikis": c, "ara": b, "varis": cc,
                        "dogrudan_km": round(dogrudan,1),
                        "ugrayarak_km": round(ugrayarak,1),
                        "sapma_%": round(sapma_orani*100,1)
                    })

    print("=== UGRAMA FIZIBILITE ANALIZI ===\n")
    print(f"Toplam talep rotasi: {len(rota_set)}")
    print(f"Ayni cikistan >=2 varisi olan merkez sayisi: {sum(1 for v in cikis_varis.values() if len(v)>=2)}")
    print(f"\nUgrama firsati (B, A-C yolu uzerinde, <%30 sapma): {len(firsatlar)}")
    if firsatlar:
        fdf = pd.DataFrame(firsatlar).sort_values("sapma_%")
        print("\nEn dusuk sapmali 15 ugrama firsati:")
        print(fdf.head(15).to_string(index=False))
        print(f"\nSapma dagilimi:")
        print(f"  <%10 sapma: {len(fdf[fdf['sapma_%']<10])} firsat (cok iyi)")
        print(f"  %10-20    : {len(fdf[(fdf['sapma_%']>=10)&(fdf['sapma_%']<20)])} firsat")
        print(f"  %20-30    : {len(fdf[fdf['sapma_%']>=20])} firsat")