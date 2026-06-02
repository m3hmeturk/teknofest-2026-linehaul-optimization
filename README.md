# Yapay Zeka Destekli Lojistik Anahat Optimizasyonu - Dataset A (MVP)

## Yaklasim
- Talep Tahmini: Rota bazli, haftanin gunune duyarli agirlikli ortalama (baseline).
- Optimizasyon: Google OR-Tools MIP (CBC). Her gun icin ayri model.
- Kiralik filo: Rotaya sabit, gunluk kira batik maliyet. Doldurma maksimize edilir.
- Spot: Kalan talep en dusuk maliyetli spot araclarla karsilanir.
- Konsolidasyon: Dataset A'da kapali (dogrudan rota).

## 11-17 Mayis Haftasi Maliyet Sonuclari

| Kalem | Tutar (TL) |
|---|---|
| Spot Arac Maliyeti | 19,931,947.45 |
| Kiralik km Maliyeti | 340,211.53 |
| Kiralik Tam Maliyet (kira dahil) | 956,211.53 |
| TOPLAM MALIYET | 20,888,158.98 |

## Ciktilar
- outputs/tahmin_talep.xlsx : Tahmin edilen talep
- outputs/arac_planlama.xlsx : Arac planlama / optimizasyon ciktisi

## Calistirma
    python main.py
