# TEKNOFEST 2026 - Lojistik Anahat Optimizasyonu (Dataset A / MVP)

## Yaklasim
- Talep Tahmini: Rota bazli, haftanin ayni gununun son 14 haftasinin
  %35 kuantili + dinamik guvenlik payi (kuantil + k*sapma, k=2.5).
- Optimizasyon: OR-Tools MIP (CBC). Her gun bagimsiz.
- Kiralik filo: rotaya sabit, ZORUNLU + oncelikli (her gun cikar).
- Spot: kalan talep en dusuk maliyetle; minimum %10 doluluk kisiti.
- Mesafe: kus ucusu (Haversine), TEK YON.
- Maliyet: kiralik (kira+km) + spot (sabit+km).
- Konsolidasyon: Dataset A'da kapali (dogrudan rota).

## 11-17 Mayis Haftasi Maliyet

| Kalem | Tutar (TL) |
|---|---|
| Spot Maliyeti | 13,381,705.41 |
| Kiralik Maliyeti (kira+km) | 802,743.90 |
| TOPLAM MALIYET | 14,184,449.31 |

## Ciktilar
- outputs/tahmin_talep.xlsx
- outputs/arac_planlama.xlsx

## Notlar
- 560 desi altindaki cok kucuk taleplerde, en kucuk arac (Kamyonet)
  bile %10 doluluga ulasamadigindan yuk yine de tasinmistir (kacinilmaz
  uc durum, ~17 satir). Yuku tasimamak yerine tasimayi tercih ettik.

## Calistirma
    python main.py
