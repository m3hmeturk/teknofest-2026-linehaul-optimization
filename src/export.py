"""
Katman 5 - Cikti Uretimi
------------------------
1) Tahmin Excel'i (tahmin_talep.xlsx)
2) Arac plani Excel'i (arac_planlama.xlsx)
3) Maliyet ozeti (README icin)
"""

import os
import pandas as pd


def _detay_str(detay):
    """ {'Tır': 1, 'Kamyon': 2} -> 'Tır x1, Kamyon x2' """
    if not detay:
        return ""
    return ", ".join(f"{t} x{n}" for t, n in detay.items())


def export_tahmin(tahmin_df, outputs_dir):
    df = tahmin_df.rename(columns={
        "cikis": "Kalkış TM",
        "varis": "Varış TM",
        "tarih": "Tarih",
        "tahmin_desi": "Tahmin Edilen Desi",
    })
    yol = os.path.join(outputs_dir, "tahmin_talep.xlsx")
    df.to_excel(yol, index=False)
    return yol


def export_plan(sonuc_df, outputs_dir):
    plan_satirlar = []   # Ana sayfa: degerlendirici icin sade format
    detay_satirlar = []  # Detay sayfasi: bizim analiz icin

    for _, r in sonuc_df.iterrows():
        kiralik_adet = sum(r["kiralik_detay"].values())
        spot_adet = sum(r["spot_detay"].values())
        toplam_maliyet = round(r["kiralik_tam_maliyet"] + r["spot_maliyet"], 2)

        # --- ANA SAYFA: tam istenen sutunlar ---
        plan_satirlar.append({
            "Tarih": r["tarih"],
            "Kalkış TM": r["cikis"],
            "Varış TM": r["varis"],
            "Kiralık Araç Sayısı": kiralik_adet,
            "Spot Araç Sayısı": spot_adet,
            "Toplam Maliyet (TL)": toplam_maliyet,
        })

        # --- DETAY SAYFASI: ek bilgiler ---
        detay_satirlar.append({
            "Tarih": r["tarih"],
            "Kalkış TM": r["cikis"],
            "Varış TM": r["varis"],
            "Talep (Desi)": r["talep_desi"],
            "Atanan Kapasite": r["atanan_kapasite"],
            "Kiralık Araç Sayısı": kiralik_adet,
            "Kiralık Detay": _detay_str(r["kiralik_detay"]),
            "Spot Araç Sayısı": spot_adet,
            "Spot Detay": _detay_str(r["spot_detay"]),
            "Kiralık Maliyet (TL)": r["kiralik_tam_maliyet"],
            "Spot Maliyet (TL)": r["spot_maliyet"],
            "Toplam Maliyet (TL)": toplam_maliyet,
        })

    plan_df = pd.DataFrame(plan_satirlar)
    detay_df = pd.DataFrame(detay_satirlar)

    yol = os.path.join(outputs_dir, "arac_planlama.xlsx")
    with pd.ExcelWriter(yol, engine="openpyxl") as writer:
        plan_df.to_excel(writer, sheet_name="Plan", index=False)
        detay_df.to_excel(writer, sheet_name="Detay", index=False)
    return yol


def maliyet_ozeti(sonuc_df):
    spot = sonuc_df["spot_maliyet"].sum()
    kiralik_km = sonuc_df["kiralik_opt_maliyet"].sum()
    kiralik_tam = sonuc_df["kiralik_tam_maliyet"].sum()
    return {
        "spot_maliyet": round(spot, 2),
        "kiralik_km_maliyet": round(kiralik_km, 2),
        "kiralik_tam_maliyet": round(kiralik_tam, 2),
        "toplam_maliyet": round(spot + kiralik_tam, 2),
    }


def write_readme(ozet, kok_dir):
    satirlar = [
        "# Yapay Zeka Destekli Lojistik Anahat Optimizasyonu - Dataset A (MVP)",
        "",
        "## Yaklasim",
        "- Talep Tahmini: Rota bazli, haftanin gunune duyarli agirlikli ortalama (baseline).",
        "- Optimizasyon: Google OR-Tools MIP (CBC). Her gun icin ayri model.",
        "- Kiralik filo: Rotaya sabit, gunluk kira batik maliyet. Doldurma maksimize edilir.",
        "- Spot: Kalan talep en dusuk maliyetli spot araclarla karsilanir.",
        "- Konsolidasyon: Dataset A'da kapali (dogrudan rota).",
        "",
        "## 11-17 Mayis Haftasi Maliyet Sonuclari",
        "",
        "| Kalem | Tutar (TL) |",
        "|---|---|",
        f"| Spot Arac Maliyeti | {ozet['spot_maliyet']:,.2f} |",
        f"| Kiralik km Maliyeti | {ozet['kiralik_km_maliyet']:,.2f} |",
        f"| Kiralik Tam Maliyet (kira dahil) | {ozet['kiralik_tam_maliyet']:,.2f} |",
        f"| TOPLAM MALIYET | {ozet['toplam_maliyet']:,.2f} |",
        "",
        "## Ciktilar",
        "- outputs/tahmin_talep.xlsx : Tahmin edilen talep",
        "- outputs/arac_planlama.xlsx : Arac planlama / optimizasyon ciktisi",
        "",
        "## Calistirma",
        "    python main.py",
        "",
    ]
    icerik = "\n".join(satirlar)
    yol = os.path.join(kok_dir, "README.md")
    with open(yol, "w", encoding="utf-8") as f:
        f.write(icerik)
    return yol