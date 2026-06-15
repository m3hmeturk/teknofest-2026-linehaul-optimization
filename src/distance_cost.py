"""
Katman 2 - Mesafe & Maliyet Matrisi
------------------------------------
- Haversine ile her TM cifti arasi km (gidis-donus icin x2).
- Her (rota x arac tipi) icin kiralik ve spot maliyetleri.
- Sabit filo karari: kiralik gunluk kira BATIK -> optimizasyon amacina
  girmez. Optimizasyon icin: kiralik = sadece km, spot = sabit + km.
"""

import math
import pandas as pd


def haversine_km(lat1, lon1, lat2, lon2):
    """Iki koordinat arasi kus ucusu mesafe (km)."""
    R = 6371.0  # Dunya yaricapi (km)
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def build_distance_matrix(koord, gidis_donus_carpani=2):
    """Tum TM ciftleri icin gidis-donus mesafesini doner.
    Cikti sutunlari: cikis, varis, tek_yon_km, gidis_donus_km"""
    merkezler = koord.set_index("Transfer Merkezi")[["Enlem", "Boylam"]].to_dict("index")
    satirlar = []
    for i, ci in merkezler.items():
        for j, cj in merkezler.items():
            if i == j:
                continue
            tek_yon = haversine_km(ci["Enlem"], ci["Boylam"], cj["Enlem"], cj["Boylam"])
            satirlar.append({
                "cikis": i,
                "varis": j,
                "tek_yon_km": round(tek_yon, 3),
                "gidis_donus_km": round(tek_yon * gidis_donus_carpani, 3),
            })
    return pd.DataFrame(satirlar)


def build_cost_table(mesafe_df, arac):
    """Her (rota x arac tipi) icin maliyetleri uretir.
    Yeni kurallar:
      - Mesafe TEK YON (gidis_donus_km artik tek yon mesafesini tasiyor;
        carpani config'de 1).
      - Kiralik ZORUNLU -> maliyeti = kira + km (tam). Optimizasyon ayrimi
        icin yine de tutuyoruz ama kiralik artik daima dispatch edilecek.
      - Spot = sabit + km.
    """
    kayitlar = []
    for _, m in mesafe_df.iterrows():
        mesafe = m["gidis_donus_km"]  # config carpani=1 oldugu icin bu TEK YON
        for _, a in arac.iterrows():
            tip = a["Araç Adı"]
            kap = a["Kapasite (desi)"]

            kiralik_kira = a["Kiralık Araç Günlük Kira (TL)"]
            kiralik_km = a["Kiralık Araç Kilometre Başına Maliyet (TL)"]
            spot_sabit = a["Spot Araç Sabit Günlük Maliyet (TL)"]
            spot_km = a["Spot Kilometre Başına Maliyet (TL)"]

            # Kiralik tam maliyet = kira + km (zorunlu, toplama dahil)
            kiralik_tam = kiralik_kira + kiralik_km * mesafe
            # Spot = sabit gunluk + km
            spot_tam = spot_sabit + spot_km * mesafe

            kayitlar.append({
                "cikis": m["cikis"],
                "varis": m["varis"],
                "arac_tipi": tip,
                "kapasite": kap,
                "mesafe_km": mesafe,
                "kiralik_maliyet": round(kiralik_tam, 2),
                "spot_maliyet": round(spot_tam, 2),
            })
    return pd.DataFrame(kayitlar)


def build_all(data, gidis_donus_carpani=None):
    koord = data["koordinatlar"]
    arac = data["arac"]
    if gidis_donus_carpani is None:
        gidis_donus_carpani = data["config"]["varsayimlar"]["gidis_donus_carpani"]

    mesafe_df = build_distance_matrix(koord, gidis_donus_carpani)
    maliyet_df = build_cost_table(mesafe_df, arac)
    return mesafe_df, maliyet_df


if __name__ == "__main__":
    from data_loader import load_all

    import os
    config_yolu = os.path.join(os.path.dirname(__file__), "..", "config.json")
    data = load_all(config_yolu)
    mesafe_df, maliyet_df = build_all(data)

    print("=== MESAFE MATRISI ===")
    print(f"Toplam yonlu rota sayisi: {len(mesafe_df)}")
    print(mesafe_df.sort_values("gidis_donus_km", ascending=False).head(3).to_string(index=False))
    print("...")
    print(mesafe_df.sort_values("gidis_donus_km").head(3).to_string(index=False))

    print("\n=== MALIYET TABLOSU ===")
    print(f"Toplam satir (rota x arac tipi): {len(maliyet_df)}")
    ornek = maliyet_df[(maliyet_df["cikis"] == "İstanbul") & (maliyet_df["varis"] == "Yalova")]
    print("\nOrnek rota Istanbul -> Yalova:")
    print(ornek[["arac_tipi", "kapasite", "mesafe_km",
                 "kiralik_maliyet", "spot_maliyet"]].to_string(index=False))