"""
Katman 3 - Talep Tahmini
------------------------
11-17 Mayis icin her rota-gun icin desi tahmini.
Yontem: her rota icin haftanin ayni gunune ait son 14 haftanin
%35'lik kuantili (ham tahmin) + dinamik guvenlik payi (k * std).
Kuantil %35 ve 14 haftalik pencere, 25+ yontemin coklu-hafta
backtest karsilastirmasiyla secildi (en dusuk WAPE + gercek talebe
karsi en iyi maliyet/ihlal dengesi).
"""

import os
import numpy as np
import pandas as pd


def _ayni_gun_son(grup, hedef_gun, son_n_hafta=14):
    """Haftanin 'hedef_gun' gunune ait son N haftanin gercek degerleri."""
    ayni = grup[grup["Tarih"].dt.dayofweek == hedef_gun].sort_values("Tarih")
    return ayni.tail(son_n_hafta)["Toplam Desi"].values


def forecast(data, son_n_hafta=14):
    desi = data["desi"]
    cfg = data["config"]["forecast"]
    bas = pd.to_datetime(cfg["hafta_baslangic"])
    bit = pd.to_datetime(cfg["hafta_bitis"])
    k = cfg.get("guvenlik_k", 2.5)
    q = cfg.get("kuantil", 0.35)
    hedef_gunler = pd.date_range(bas, bit, freq="D")

    rotalar = desi.groupby(["Çıkış Transfer Merkezi", "Varış Transfer Merkezi"])

    kayitlar = []
    for (cikis, varis), grup in rotalar:
        for tarih in hedef_gunler:
            son = _ayni_gun_son(grup, tarih.dayofweek, son_n_hafta)
            if len(son) == 0:
                ham = grup["Toplam Desi"].median() if len(grup) else 0.0
                sap = 0.0
            else:
                ham = float(np.quantile(son, q))   # kuantil %35 tahmin
                sap = float(np.std(son))
            planlanan = max(ham + k * sap, 0.0)
            kayitlar.append({
                "cikis": cikis,
                "varis": varis,
                "tarih": tarih.date(),
                "ham_tahmin": round(max(ham, 0.0), 2),
                "tahmin_desi": round(planlanan, 2),
            })
    return pd.DataFrame(kayitlar)


def build_all(data, son_n_hafta=14):
    return forecast(data, son_n_hafta)


if __name__ == "__main__":
    from data_loader import load_all

    config_yolu = os.path.join(os.path.dirname(__file__), "..", "config.json")
    data = load_all(config_yolu)
    tahmin_df = build_all(data)

    print("=== TALEP TAHMINI (11-17 Mayis) ===")
    print(f"Toplam tahmin satiri: {len(tahmin_df)}")
    print(f"Benzersiz rota sayisi: {tahmin_df.groupby(['cikis','varis']).ngroups}")
    print(f"Tahmin edilen gun sayisi: {tahmin_df['tarih'].nunique()}")
    print(f"\nToplam haftalik tahmini desi: {tahmin_df['tahmin_desi'].sum():,.0f}")
    print("\nOrnek (ilk 10 satir):")
    print(tahmin_df.head(10).to_string(index=False))

    # Hizli mantik kontrolu: gunluk toplam talep
    gunluk = tahmin_df.groupby("tarih")["tahmin_desi"].sum()
    print("\nGunluk toplam tahmini desi:")
    print(gunluk.to_string())