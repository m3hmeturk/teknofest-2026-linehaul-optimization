"""
Katman 3 - Talep Tahmini (Baseline)
-----------------------------------
11-17 Mayis icin her rota icin gunluk desi tahmini.
Baseline: her rota icin haftanin ayni gunune ait son N haftanin
agirlikli ortalamasi (yakin haftalara daha cok agirlik).
"""

import os
import numpy as np
import pandas as pd


def _hafta_gunu_ort_sapma(grup, hedef_gun, son_n_hafta=6):
    """Haftanin 'hedef_gun' gunune ait son N haftanin agirlikli ortalamasi
    VE standart sapmasi. (ortalama, sapma) doner."""
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


def forecast(data, son_n_hafta=6):
    desi = data["desi"]
    cfg = data["config"]["forecast"]
    bas = pd.to_datetime(cfg["hafta_baslangic"])
    bit = pd.to_datetime(cfg["hafta_bitis"])
    k = cfg.get("guvenlik_k", 0.0)  # dinamik guvenlik payi katsayisi
    hedef_gunler = pd.date_range(bas, bit, freq="D")

    rotalar = desi.groupby(["Çıkış Transfer Merkezi", "Varış Transfer Merkezi"])

    kayitlar = []
    for (cikis, varis), grup in rotalar:
        for tarih in hedef_gunler:
            ort, sap = _hafta_gunu_ort_sapma(grup, tarih.dayofweek, son_n_hafta)
            # Ham tahmin (referans) ve guvenlik payli planlama degeri
            ham = max(ort, 0.0)
            planlanan = max(ort + k * sap, 0.0)
            kayitlar.append({
                "cikis": cikis,
                "varis": varis,
                "tarih": tarih.date(),
                "ham_tahmin": round(ham, 2),
                "tahmin_desi": round(planlanan, 2),  # optimizasyon bunu kullanir
            })
    return pd.DataFrame(kayitlar)


def build_all(data, son_n_hafta=6):
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