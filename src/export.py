"""
Katman 5 - Cikti Uretimi (YENI FORMAT)
--------------------------------------
- Tahmin: Tarih, Çıkış TM, Varış TM, Tahmin Edilen Desi
- Plan: her satir TEK ARAC -> Tarih, Araç Tipi, Çıkış TM, Varış TM,
        Atanan Desi, Maliyet
"""

import os
import pandas as pd


def export_tahmin(tahmin_df, outputs_dir):
    df = tahmin_df.rename(columns={
        "tarih": "Tarih",
        "cikis": "Çıkış TM",
        "varis": "Varış TM",
        "tahmin_desi": "Tahmin Edilen Desi",
    })[["Tarih", "Çıkış TM", "Varış TM", "Tahmin Edilen Desi"]]
    yol = os.path.join(outputs_dir, "tahmin_talep.xlsx")
    df.to_excel(yol, index=False)
    return yol


def _arac_basina_dagit(r, arac_kap, maliyet_lk):
    """Bir rota-gun satirini ARAC BASINA satirlara patlatir.
    Talebi araclara dagitir: once kiralik doldur, kalani spota."""
    cikis, varis, tarih = r["cikis"], r["varis"], r["tarih"]
    kalan_talep = r["talep_desi"]
    satirlar = []

    # 1) Kiralik araclar (her biri ayri satir)
    for tip, adet in r["kiralik_detay"].items():
        kap = arac_kap[tip]
        birim_maliyet = maliyet_lk[(cikis, varis, tip)]["kiralik_maliyet"]
        for _ in range(adet):
            atanan = min(kalan_talep, kap)
            atanan = max(atanan, 0)
            satirlar.append({
                "Tarih": tarih,
                "Araç Tipi": f"Kiralık {tip}",
                "Çıkış TM": cikis,
                "Varış TM": varis,
                "Atanan Desi": round(atanan, 2),
                "Maliyet": round(birim_maliyet, 2),
            })
            kalan_talep -= atanan

    # 2) Spot araclar (her biri ayri satir)
    for tip, adet in r["spot_detay"].items():
        kap = arac_kap[tip]
        birim_maliyet = maliyet_lk[(cikis, varis, tip)]["spot_maliyet"]
        for _ in range(adet):
            atanan = min(kalan_talep, kap)
            atanan = max(atanan, 0)
            satirlar.append({
                "Tarih": tarih,
                "Araç Tipi": f"Spot {tip}",
                "Çıkış TM": cikis,
                "Varış TM": varis,
                "Atanan Desi": round(atanan, 2),
                "Maliyet": round(birim_maliyet, 2),
            })
            kalan_talep -= atanan

    return satirlar


def export_plan(sonuc_df, arac_kap, maliyet_lk, outputs_dir):
    plan_satirlar = []
    for _, r in sonuc_df.iterrows():
        plan_satirlar.extend(_arac_basina_dagit(r, arac_kap, maliyet_lk))

    plan_df = pd.DataFrame(plan_satirlar)
    yol = os.path.join(outputs_dir, "arac_planlama.xlsx")
    plan_df.to_excel(yol, index=False)
    return yol, plan_df


def maliyet_ozeti(sonuc_df):
    spot = sonuc_df["spot_maliyet"].sum()
    kiralik = sonuc_df["kiralik_maliyet"].sum()
    return {
        "spot_maliyet": round(spot, 2),
        "kiralik_maliyet": round(kiralik, 2),
        "toplam_maliyet": round(spot + kiralik, 2),
    }


def write_readme(ozet, kok_dir):
    satirlar = [
        "# TEKNOFEST 2026 - Lojistik Anahat Optimizasyonu (Dataset A / MVP)",
        "",
        "## Yaklasim",
        "- Talep Tahmini: Rota bazli, haftanin ayni gununun son 14 haftasinin",
        "  %35 kuantili + dinamik guvenlik payi (kuantil + k*sapma, k=2.5).",
        "- Optimizasyon: OR-Tools MIP (CBC). Her gun bagimsiz.",
        "- Kiralik filo: rotaya sabit, ZORUNLU + oncelikli (her gun cikar).",
        "- Spot: kalan talep en dusuk maliyetle; minimum %10 doluluk kisiti.",
        "- Mesafe: kus ucusu (Haversine), TEK YON.",
        "- Maliyet: kiralik (kira+km) + spot (sabit+km).",
        "- Konsolidasyon: Dataset A'da kapali (dogrudan rota).",
        "",
        "## 11-17 Mayis Haftasi Maliyet",
        "",
        "| Kalem | Tutar (TL) |",
        "|---|---|",
        f"| Spot Maliyeti | {ozet['spot_maliyet']:,.2f} |",
        f"| Kiralik Maliyeti (kira+km) | {ozet['kiralik_maliyet']:,.2f} |",
        f"| TOPLAM MALIYET | {ozet['toplam_maliyet']:,.2f} |",
        "",
        "## Ciktilar",
        "- outputs/tahmin_talep.xlsx",
        "- outputs/arac_planlama.xlsx",
        "",
        "## Notlar",
        "- 560 desi altindaki cok kucuk taleplerde, en kucuk arac (Kamyonet)",
        "  bile %10 doluluga ulasamadigindan yuk yine de tasinmistir (kacinilmaz",
        "  uc durum, ~17 satir). Yuku tasimamak yerine tasimayi tercih ettik.",
        "",
        "## Calistirma",
        "    python main.py",
        "",
    ]
    yol = os.path.join(kok_dir, "README.md")
    with open(yol, "w", encoding="utf-8") as f:
        f.write("\n".join(satirlar))
    return yol