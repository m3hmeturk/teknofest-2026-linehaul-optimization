"""
Orkestratör - Tum katmanlari sirayla calistirir.
Kullanim: python main.py   (kok klasorden)
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from data_loader import load_all
from distance_cost import build_all as build_costs
from forecast import build_all as build_forecast
from optimizer import optimize
from export import export_tahmin, export_plan, maliyet_ozeti, write_readme


def main():
    kok = os.path.dirname(os.path.abspath(__file__))
    config_yolu = os.path.join(kok, "config.json")
    outputs_dir = os.path.join(kok, "outputs")
    os.makedirs(outputs_dir, exist_ok=True)

    print("[1/5] Veri yukleniyor...")
    data = load_all(config_yolu)

    print("[2/5] Mesafe & maliyet matrisi...")
    mesafe_df, maliyet_df = build_costs(data)

    print("[3/5] Talep tahmini...")
    tahmin_df = build_forecast(data)

    print("[4/5] Optimizasyon...")
    sonuc_df = optimize(data, mesafe_df, maliyet_df, tahmin_df)

    print("[5/5] Ciktilar yaziliyor...")
    t_yol = export_tahmin(tahmin_df, outputs_dir)
    p_yol = export_plan(sonuc_df, outputs_dir)
    ozet = maliyet_ozeti(sonuc_df)
    r_yol = write_readme(ozet, kok)

    print("\n=== TAMAMLANDI ===")
    print(f"Tahmin       : {t_yol}")
    print(f"Arac plani   : {p_yol}")
    print(f"README       : {r_yol}")
    print(f"\nTOPLAM MALIYET: {ozet['toplam_maliyet']:,.2f} TL")
    print(f"  Spot        : {ozet['spot_maliyet']:,.2f} TL")
    print(f"  Kiralik tam : {ozet['kiralik_tam_maliyet']:,.2f} TL")


if __name__ == "__main__":
    main()