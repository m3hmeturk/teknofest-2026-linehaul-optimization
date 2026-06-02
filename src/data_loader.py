"""
Katman 1 - Veri Yukleme & Dogrulama
------------------------------------
4 Excel dosyasini okur, isimleri normalize eder, eksik koordinatlari
(config.json'daki duzeltmeler) ekler ve veri tutarliligini dogrular.
Cikti: temizlenmis 4 DataFrame + bir dogrulama raporu.
"""

import json
import os
import pandas as pd


def load_config(config_path="config.json"):
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _norm(s):
    """TM isimlerini normalize eder. Turkce buyuk/kucuk tuzaklarina
    girmemek icin SADECE bosluk temizligi yapariz, harf donusumu yok."""
    if isinstance(s, str):
        return s.strip()
    return s


def _find_file(folder, anahtarlar):
    """Klasorde, verilen anahtar kelimelerin hepsini iceren ilk .xlsx'i bulur.
    Turkce karakter / alt cizgi farklarina takilmaz."""
    import unicodedata

    def sade(t):
        t = t.replace("ı", "i").replace("İ", "i")
        t = unicodedata.normalize("NFKD", t)
        t = "".join(c for c in t if not unicodedata.combining(c))
        return t.lower().replace("_", "").replace(" ", "")

    for fname in os.listdir(folder):
        if not fname.lower().endswith(".xlsx"):
            continue
        if all(sade(k) in sade(fname) for k in anahtarlar):
            return os.path.join(folder, fname)
    raise FileNotFoundError(f"{anahtarlar} icin dosya bulunamadi: {folder}")


def load_raw(config):
    base = os.path.dirname(os.path.abspath(config.get("_config_path", "config.json")))
    data_dir = os.path.join(base, "data")

    koord = pd.read_excel(_find_file(data_dir, ["koordinat"]))
    kiralik = pd.read_excel(_find_file(data_dir, ["kiralik"]))
    desi = pd.read_excel(_find_file(data_dir, ["desi"]))
    arac = pd.read_excel(_find_file(data_dir, ["kapasite"]))
    return koord, kiralik, desi, arac


def clean_koordinatlar(koord, config):
    koord = koord.copy()
    koord["Transfer Merkezi"] = koord["Transfer Merkezi"].map(_norm)

    # Eksik koordinatlari ekle (Kocaeli vb.)
    eksik = config.get("veri_duzeltmeleri", {}).get("eksik_koordinatlar", {})
    mevcut = set(koord["Transfer Merkezi"])
    yeni_satirlar = []
    for tm, c in eksik.items():
        if tm not in mevcut:
            yeni_satirlar.append(
                {"Transfer Merkezi": tm, "Enlem": c["enlem"], "Boylam": c["boylam"]}
            )
    if yeni_satirlar:
        koord = pd.concat([koord, pd.DataFrame(yeni_satirlar)], ignore_index=True)

    return koord


def clean_kiralik(kiralik):
    kiralik = kiralik.copy()
    kiralik["Çıkış Transfer Merkezi"] = kiralik["Çıkış Transfer Merkezi"].map(_norm)
    kiralik["Varış Transfer Merkezi"] = kiralik["Varış Transfer Merkezi"].map(_norm)
    kiralik["Araç Türü"] = kiralik["Araç Türü"].map(_norm)
    return kiralik


def clean_desi(desi):
    desi = desi.copy()
    desi["Çıkış Transfer Merkezi"] = desi["Çıkış Transfer Merkezi"].map(_norm)
    desi["Varış Transfer Merkezi"] = desi["Varış Transfer Merkezi"].map(_norm)
    desi["Tarih"] = pd.to_datetime(desi["Tarih"])
    return desi


def clean_arac(arac):
    arac = arac.copy()
    arac["Araç Adı"] = arac["Araç Adı"].map(_norm)
    return arac


def validate(koord, kiralik, desi, arac):
    """Veri tutarliligini kontrol eder. Sorun varsa rapor doner."""
    rapor = []
    koord_set = set(koord["Transfer Merkezi"])

    # 1) Talepteki tum merkezler koordinatta var mi?
    talep_merkez = set(desi["Çıkış Transfer Merkezi"]) | set(desi["Varış Transfer Merkezi"])
    rapor.append(("Talepte olup koordinatta olmayan merkez", sorted(talep_merkez - koord_set)))

    # 2) Kiralik araclarin merkezleri koordinatta var mi?
    kir_merkez = set(kiralik["Çıkış Transfer Merkezi"]) | set(kiralik["Varış Transfer Merkezi"])
    rapor.append(("Kiralikta olup koordinatta olmayan merkez", sorted(kir_merkez - koord_set)))

    # 3) Kiralik arac turleri maliyet tablosunda var mi?
    arac_set = set(arac["Araç Adı"])
    rapor.append(("Kiralikta olup maliyet tablosunda olmayan arac turu",
                  sorted(set(kiralik["Araç Türü"]) - arac_set)))

    # 4) Negatif / sifir talep var mi?
    rapor.append(("Sifir/negatif desi satir sayisi", len(desi[desi["Toplam Desi"] <= 0])))

    # 5) Eksik (NaN) deger var mi?
    rapor.append(("Desi NaN satir sayisi", int(desi["Toplam Desi"].isna().sum())))

    return rapor


def load_all(config_path="config.json"):
    config = load_config(config_path)
    config["_config_path"] = config_path

    koord, kiralik, desi, arac = load_raw(config)
    koord = clean_koordinatlar(koord, config)
    kiralik = clean_kiralik(kiralik)
    desi = clean_desi(desi)
    arac = clean_arac(arac)

    rapor = validate(koord, kiralik, desi, arac)
    return {
        "koordinatlar": koord,
        "kiralik": kiralik,
        "desi": desi,
        "arac": arac,
        "config": config,
        "rapor": rapor,
    }


if __name__ == "__main__":
    data = load_all("config.json")
    print("=== VERI YUKLEME OZETI ===")
    print(f"Koordinatlar : {data['koordinatlar'].shape[0]} merkez")
    print(f"Kiralik      : {data['kiralik'].shape[0]} satir, "
          f"{int(data['kiralik']['Araç sayısı'].sum())} arac")
    print(f"Desi talep   : {data['desi'].shape[0]} satir, "
          f"{data['desi']['Tarih'].dt.date.nunique()} gun")
    print(f"Arac tipleri : {data['arac'].shape[0]} tip")

    print("\n=== DOGRULAMA RAPORU ===")
    sorun_var = False
    for ad, sonuc in data["rapor"]:
        durum = "OK" if (sonuc == [] or sonuc == 0) else "DIKKAT"
        if durum == "DIKKAT":
            sorun_var = True
        print(f"[{durum}] {ad}: {sonuc}")

    print("\nSONUC:", "Tum kontroller temiz." if not sorun_var
          else "Yukaridaki uyarilara bak.")