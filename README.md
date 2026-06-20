# TEKNOFEST 2026 — Yapay Zeka Destekli Lojistik Anahat (Linehaul) Optimizasyonu

**Aşama:** Temel İşlevli Çözüm (MVP) — Dataset A

Bu depo, HepsiJET transfer merkezleri arasındaki haftalık kargo (desi) talebini tahminleyip, bu talebi en düşük maliyetle karşılayan araç planını üreten uçtan uca bir çözümü içerir. Hedef hafta: **11–17 Mayıs 2026**.

---

## Sonuç Özeti

| Kalem | Tutar (TL) |
|---|---|
| Spot Maliyeti | 13,381,705.41 |
| Kiralık Maliyeti (kira + km) | 802,743.90 |
| **TOPLAM MALİYET** | **14,184,449.31** |

- **Tahmin başarısı (WAPE):** %24.09 (çoklu-hafta backtest ortalaması)
- **Gerçek talebi karşılama:** ~%99.8 (4 haftalık backtest'te haftada ~1 ihlal)

---

## Çözüm Mimarisi

Çözüm 5 katmanlı bir boru hattıdır; `main.py` hepsini sırayla çalıştırır:

| Katman | Dosya | Görev |
|---|---|---|
| 1 | `src/data_loader.py` | 4 Excel'i okur, normalize eder, tutarlılığı doğrular |
| 2 | `src/distance_cost.py` | Haversine (tek yön) mesafe + araç maliyet tablosu |
| 3 | `src/forecast.py` | Talep tahmini (kuantil %35 + güvenlik payı) |
| 4 | `src/optimizer.py` | OR-Tools MIP ile araç optimizasyonu |
| 5 | `src/export.py` | Excel çıktıları + maliyet özeti |

---

## Yöntem ve Varsayımlar

Aşağıdaki kurallar resmi teknik bülten ve SSS (FAQ) oturumundan alınmıştır:

- **Mesafe:** Kuş uçuşu (Haversine), **tek yön** (araç dönüşü hesaba katılmaz).
- **Kiralık filo:** Rotaya sabit, **zorunlu ve öncelikli** — her gün rotasında çıkar (talep olmasa dahi). Maliyeti (kira + km) toplama dahildir.
- **Spot araç:** Kiralık kapasitesini aşan kalan talebi karşılar. Sınırsız sayıda çağrılabilir. **Minimum %10 doluluk** kısıtı uygulanır.
- **Maliyet:** Kiralık = kira + km; Spot = sabit günlük + km.
- **Konsolidasyon:** Dataset A'da kapalı (doğrudan rota).
- **Her gün bağımsız** değerlendirilir; araçlar tanımlı başlangıç konumlarından hareket eder.

### Talep Tahmini

Her rota–gün için, haftanın aynı gününe ait **son 14 haftanın %35'lik kuantili** ham tahmin olarak alınır; üzerine o serinin standart sapmasının **2.5 katı** dinamik güvenlik payı eklenir.

Bu yöntem rastgele seçilmemiştir: **25'ten fazla tahmin yöntemi** çoklu-hafta backtest ile karşılaştırılmıştır (ağırlıklı ortalama, medyan, LightGBM, Holt-Winters, EWMA, Huber, trend, geometrik ortalama, adaptif güvenlik payı vb.). Bu yüksek varyanslı/kaotik talep yapısında, **robust kuantil yaklaşımı** karmaşık makine öğrenmesi ve trend modellerinden tutarlı biçimde üstün çıkmıştır. Karşılaştırma kodları `analiz/` klasöründedir.

### Optimizasyon

Her rota–gün için kiralık araçlar (zorunlu) yerleştirildikten sonra kalan talep, OR-Tools CBC çözücüsüyle en düşük maliyetli spot araç kombinasyonuna atanır. Minimum %10 doluluk kısıtı modele dahildir.

---

## Klasör Yapısı
.

├── main.py                  # Tüm boru hattını çalıştırır

├── config.json              # Parametreler (kuantil, k, hafta, varsayımlar)

├── requirements.txt

├── data/                    # Girdi Excel dosyaları

├── src/                     # Çözüm modülleri (5 katman)

├── analiz/                  # Yöntem karşılaştırma / araştırma scriptleri

└── outputs/                 # Üretilen çıktılar

├── tahmin_talep.xlsx

├── arac_planlama.xlsx

└── maliyet_ozeti.txt

> `analiz/` klasörü, tahmin yöntemi seçimindeki backtest karşılaştırmalarını ve uğrama (multi-stop) fizibilite analizlerini içerir. Çözümün parçası değildir; yöntem gerekçelerinin kanıtı olarak saklanmıştır.

---

## Çıktı Formatları

**tahmin_talep.xlsx** — her satır bir TM–gün–desi:

| Tarih | Çıkış TM | Varış TM | Tahmin Edilen Desi |
|---|---|---|---|

**arac_planlama.xlsx** — her satır tek bir araç ataması:

| Tarih | Araç Tipi | Çıkış TM | Varış TM | Atanan Desi | Maliyet |
|---|---|---|---|---|---|

---

## Kurulum ve Çalıştırma

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

Çıktılar `outputs/` klasörüne yazılır.

---

## Notlar

- 560 desi altındaki çok küçük taleplerde, en küçük araç (Kamyonet) bile %10 doluluğa ulaşamadığından yük yine de taşınmıştır. Bu, fiziksel olarak kaçınılmaz bir uç durumdur (~14–17 satır); yükü taşımamak yerine taşımayı tercih ettik.