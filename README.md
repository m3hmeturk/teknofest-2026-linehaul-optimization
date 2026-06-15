# TEKNOFEST 2026 - Lojistik Anahat Optimizasyonu (Dataset A / MVP)

## Yaklasim
- Talep Tahmini: Rota bazli, haftanin gunune duyarli agirlikli ortalama
  + dinamik guvenlik payi (ort + k*sapma).
- Optimizasyon: OR-Tools MIP (CBC). Her gun bagimsiz.
- Kiralik filo: rotaya sabit, ZORUNLU + oncelikli (her gun cikar).
- Spot: kalan talep en dusuk maliyetle; minimum %10 doluluk kisiti.
- Mesafe: kus ucusu (Haversine), TEK YON.
- Maliyet: kiralik (kira+km) + spot (sabit+km).
- Konsolidasyon: Dataset A'da kapali (dogrudan rota).

## 11-17 Mayis Haftasi Maliyet

| Kalem | Tutar (TL) |
|---|---|
| Spot Maliyeti | 13,586,339.64 |
| Kiralik Maliyeti (kira+km) | 802,743.90 |
| TOPLAM MALIYET | 14,389,083.54 |

## Ciktilar
- outputs/tahmin_talep.xlsx
- outputs/arac_planlama.xlsx

## Notlar
- 560 desi altindaki cok kucuk taleplerde, en kucuk arac (Kamyonet)
  bile %10 doluluga ulasamadigindan yuk yine de tasinmistir (kacinilmaz
  uc durum, ~17 satir). Yuku tasimamak yerine tasimayi tercih ettik.

## Calistirma
    python main.py
