#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
USTAD GÖZCÜ — yerel sunucu + veri köprüsü
=========================================
Panel tek dosya HTML olarak çalışamaz, çünkü veri kaynakları tarayıcıya
CORS izni vermiyor. Bu sunucu iki işi yapar:

  1) harita/ klasörünü site olarak yayınlar
  2) /veri/... uçlarından dış kaynaklara sunucu tarafında gidip veriyi
     tarayıcıya temiz JSON olarak verir (CORS sorunu kalmaz)

Kullanım:  python sunucu.py          → http://127.0.0.1:8811
           python sunucu.py 9000     → başka port

Sadece Python standart kütüphanesi kullanılır. Tek istisna: uydu yörünge
hesabı için `sgp4` kütüphanesi proje içine gömülüdür (harita/kutuphane/).

NOT — veri kaynağına saygı:
  ADS-B ve AIS ağları gönüllü topluluk sunucularıdır. Bu yüzden istekler
  önbelleklenir, eşzamanlılık sınırlıdır ve 429 (çok istek) yanıtı
  gelirse kaynak değiştirilip geri çekilinir.
"""

import csv
import gzip
import io
import json
import math
import os
import socket
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

# ----------------------------------------------------------------------------
# Ayarlar
# ----------------------------------------------------------------------------

PORT = 8811
KOK = os.path.dirname(os.path.abspath(__file__))          # harita/
PROJE = os.path.dirname(KOK)                              # USTAD-GOZCU/
ONBELLEK = os.path.join(PROJE, "veri", "onbellek")
AYAR_YOLU = os.path.join(PROJE, "ayar.json")
SURUM = "0.15.1"

# Gömülü kütüphane (sgp4) — sistemde kurulu olmasına gerek kalmasın
KUTUPHANE = os.path.join(KOK, "kutuphane")
if os.path.isdir(KUTUPHANE) and KUTUPHANE not in sys.path:
    sys.path.insert(0, KUTUPHANE)

UA = "UstadGozcu/0.3 (+https://ustadkenankuzucu.com.tr)"

# Uçak kaynakları: ad → (kare şablonu, kayıt anahtarı, açıklama)
UCAK_KAYNAKLARI = {
    "adsb.lol": ("https://api.adsb.lol/v2/point/{lat}/{lon}/250", "ac",
                 "Dünya geneli, iyi kapsama"),
    "adsb.fi": ("https://opendata.adsb.fi/api/v2/lat/{lat}/lon/{lon}/dist/250", "ac",
                "Kuzey Avrupa ağırlıklı, Türkiye'de biraz daha iyi"),
}
KAYNAK_SIRA = ["adsb.lol", "adsb.fi"]

# Önbellek süreleri (saniye)
TTL_UCAK_KARE = 60          # tek bir 250 nm karesi
TTL_DEPREM = 120
TTL_HAVAALANI = 86400
TTL_ARAMA = 3600
TTL_HAVA_DOSYA = 6 * 86400  # OurAirports CSV diskte
TTL_GEMI = 30
TTL_EONET = 900
TTL_TLE = 6 * 3600          # uydu yörünge elemanları
TTL_UYDU_KONUM = 10
TTL_KABLO = 86400
TTL_DUNYA = 900             # dünya uçak anlık görüntüsü (OpenSky kotası için)

# Aynı anda kaç kare isteği (topluluk sunucusunu yormamak için).
# Bunlar gönüllü ağlar: saniyede birden fazla istek atarsak bizi kapatıyorlar.
ES_ZAMANLI = 2
EN_FAZLA_KARE = 16
ISTEK_ARALIK = 1.2          # aynı kaynağa iki istek arası en az saniye

_onbellek = {}
_onbellek_kilit = threading.Lock()

# 429 alınca kaynağı geçici olarak devre dışı bırak.
# Üst üste yersen süre katlanarak artar (90 → 180 → 360 → 720 → en fazla 900 sn).
_kaynak_ceza = {}
_ceza_sayaci = {}
_ceza_kilit = threading.Lock()

_son_istek = {}
_rate_kilit = threading.Lock()


def _istek_izni(kaynak):
    """Aynı kaynağa ISTEK_ARALIK'tan sık istek atmayı engeller."""
    with _rate_kilit:
        bekle = _son_istek.get(kaynak, 0) + ISTEK_ARALIK - time.time()
    if bekle > 0:
        time.sleep(min(bekle, 5.0))
    with _rate_kilit:
        _son_istek[kaynak] = time.time()


def _ceza_sifirla(kaynak):
    with _ceza_kilit:
        _ceza_sayaci[kaynak] = 0


# ----------------------------------------------------------------------------
# Yardımcılar
# ----------------------------------------------------------------------------

def ayar_oku():
    try:
        with open(AYAR_YOLU, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _cache_al(anahtar, ttl, uret):
    simdi = time.time()
    with _onbellek_kilit:
        kayit = _onbellek.get(anahtar)
        if kayit and simdi - kayit[0] < ttl:
            return kayit[1]
    deger = uret()
    with _onbellek_kilit:
        _onbellek[anahtar] = (simdi, deger)
    return deger


def _cache_koy(anahtar, deger):
    with _onbellek_kilit:
        _onbellek[anahtar] = (time.time(), deger)


def indir(url, zaman_asimi=25, ek_baslik=None):
    """
    Gzip'i şeffaf biçimde çözer: bazı sunucular (Finlandiya AIS) gzip
    şartı koyar ve gzip'li yanıt verir, bazıları düz JSON verir.
    İkisi de çalışır — magic byte kontrolü yapılır.
    """
    baslik = {
        "User-Agent": UA,
        "Accept": "application/json,text/csv,*/*",
        "Accept-Encoding": "gzip",
    }
    if ek_baslik:
        baslik.update(ek_baslik)
    istek = urllib.request.Request(url, headers=baslik)
    with urllib.request.urlopen(istek, timeout=zaman_asimi) as yanit:
        ham = yanit.read()
        kodlama = (yanit.headers.get("Content-Encoding") or "").lower()
    if kodlama == "gzip" or ham[:2] == b"\x1f\x8b":
        ham = gzip.decompress(ham)
    return ham


def json_indir(url, zaman_asimi=25):
    return json.loads(indir(url, zaman_asimi).decode("utf-8", "replace"))


def onbellek_yolu(ad):
    os.makedirs(ONBELLEK, exist_ok=True)
    return os.path.join(ONBELLEK, ad)


def diskten_json(ad, ttl, uret):
    """Büyük dosyalar için diskte JSON önbelleği."""
    yol = onbellek_yolu(ad)
    if os.path.exists(yol) and (time.time() - os.path.getmtime(yol) < ttl):
        try:
            with open(yol, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    deger = uret()
    try:
        with open(yol, "w", encoding="utf-8") as f:
            json.dump(deger, f, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        pass
    return deger


# ----------------------------------------------------------------------------
# UÇAKLAR
# ----------------------------------------------------------------------------

def _kaynak_cezali(kaynak):
    with _ceza_kilit:
        bitis = _kaynak_ceza.get(kaynak, 0)
    return time.time() < bitis


def _kaynak_cezalandir(kaynak, saniye=None):
    with _ceza_kilit:
        n = _ceza_sayaci.get(kaynak, 0) + 1
        _ceza_sayaci[kaynak] = n
        sure = saniye if saniye else min(90 * (2 ** (n - 1)), 900)
        _kaynak_ceza[kaynak] = time.time() + sure
    sys.stderr.write("  ~ %s kaynagi %d sn devre disi (cok istek)\n" % (kaynak, sure))


def _kare_cek(kaynak, lat, lon):
    """Tek bir 250 deniz mili dairesi. Hata olursa boş liste değil, None."""
    sablon, anahtar = UCAK_KAYNAKLARI[kaynak][0], UCAK_KAYNAKLARI[kaynak][1]
    url = sablon.format(lat=round(lat, 3), lon=round(lon, 3))
    _istek_izni(kaynak)
    try:
        veri = json_indir(url, 25)
        kayit = veri.get(anahtar) or veri.get("aircraft") or []
        _ceza_sifirla(kaynak)
        return kayit
    except urllib.error.HTTPError as hata:
        if hata.code == 429:
            _kaynak_cezalandir(kaynak)
        return None
    except Exception:
        return None


def _kareler(bbox, en_fazla=EN_FAZLA_KARE):
    """Görünen alanı 250 nm'lik dairelerle kaplar. bbox=(g,b,k,d)"""
    g, b, k, d = bbox
    g = max(g, -84.0)
    k = min(k, 84.0)
    if d <= b:
        d = b

    orta_enlem = (g + k) / 2.0
    enlem_adim = 3.6
    boylam_adim = max(3.6 / max(math.cos(math.radians(orta_enlem)), 0.18), 0.8)

    n_enlem = max(1, int((k - g) / enlem_adim) + 1)
    n_boylam = max(1, int((d - b) / boylam_adim) + 1)
    while n_enlem * n_boylam > en_fazla:
        enlem_adim *= 1.3
        boylam_adim *= 1.3
        n_enlem = max(1, int((k - g) / enlem_adim) + 1)
        n_boylam = max(1, int((d - b) / boylam_adim) + 1)

    noktalar = []
    for i in range(n_enlem):
        lat = min(g + (i + .5) * enlem_adim, 83.0)
        for j in range(n_boylam):
            lon = b + (j + .5) * boylam_adim
            if lon > 180:
                lon -= 360
            noktalar.append((lat, lon))
    return noktalar


def _ucak_kisalt(a):
    lat, lon = a.get("lat"), a.get("lon")
    if lat is None or lon is None:
        return None
    alt = a.get("alt_baro")
    yerde = alt == "ground"
    if yerde:
        alt_sayi = 0
    elif isinstance(alt, (int, float)):
        alt_sayi = alt
    else:
        alt_sayi = a.get("alt_geom") or 0
    cagri = (a.get("flight") or "").strip()
    try:
        return {
            "h": a.get("hex"),
            "c": cagri or None,
            "r": a.get("r"),
            "t": a.get("t"),
            "la": round(float(lat), 5),
            "lo": round(float(lon), 5),
            "a": int(alt_sayi or 0),
            "g": round(float(a.get("gs") or 0), 1),
            "d": round(float(a.get("track") or a.get("true_heading") or 0), 1),
            "v": round(float(a.get("baro_rate") or 0)),
            "y": 1 if yerde else 0,
            "s": a.get("squawk"),
        }
    except (TypeError, ValueError):
        return None


def _opensky_ucak(st):
    """OpenSky durum vektörünü adsb.lol biçimine çevirir."""
    try:
        if not st or st[5] is None or st[6] is None:
            return None
        yerde = bool(st[8])
        alt_m = st[7] if st[7] is not None else st[13]
        return {
            "hex": (st[0] or "").lower(),
            "flight": (st[1] or "").strip() or None,
            "lat": st[6], "lon": st[5],
            "alt_baro": "ground" if yerde else (
                round(alt_m * 3.28084) if alt_m is not None else None),
            "gs": round((st[9] or 0) * 1.94384, 1),
            "track": st[10],
            "baro_rate": round((st[11] or 0) * 196.85),
            "squawk": st[14],
        }
    except (TypeError, ValueError, IndexError):
        return None


def _opensky_kutu(bbox):
    """Tek istekte kutunun tamamı. Kare kare sormaktan çok daha nazik."""
    g, b, k, d = bbox
    url = ("https://opensky-network.org/api/states/all?lamin=%s&lomin=%s&lamax=%s&lomax=%s"
           % (round(max(g, -89.0), 3), round(b, 3), round(min(k, 89.0), 3), round(d, 3)))
    _istek_izni("opensky")
    try:
        veri = json_indir(url, 35)
        _ceza_sifirla("opensky")
        return [u for u in (_opensky_ucak(s) for s in (veri.get("states") or [])) if u]
    except urllib.error.HTTPError as hata:
        if hata.code == 429:
            _kaynak_cezalandir("opensky")
        return None
    except Exception:
        return None


def _dunya_anlik():
    """
    OpenSky'nin tam anlık görüntüsü: TEK istekte bütün dünyadaki uçaklar
    (yaklaşık 9.000 kayıt, ~1,2 MB). Gönüllü ağlara kare kare sormaktan
    çok daha nazik; o yüzden 15 dakika önbelleklenir (anonim günlük kotayı
    aşmamak için).
    """
    _istek_izni("opensky")
    try:
        veri = json_indir("https://opensky-network.org/api/states/all", 45)
        _ceza_sifirla("opensky")
        return [u for u in (_opensky_ucak(s) for s in (veri.get("states") or [])) if u]
    except urllib.error.HTTPError as hata:
        if hata.code == 429:
            _kaynak_cezalandir("opensky")
        return None
    except Exception:
        return None


def ucaklar(kaynak, bbox, dunya=False):
    """
    Üç yol var:
      0) dunya=1  → bütün dünya, tek istek, 15 dk önbellek (giriş ekranı).
      1) Çok geniş görünüm → aynı dünya anlık görüntüsü kutuya göre süzülür.
      2) Orta görünüm (>6 kare) → OpenSky'den tek istekte bütün kutu.
      3) Yakın görünüm → adsb.lol / adsb.fi 250 nm kareler, önbellekli.
    Kaynak sınırlarsa son bilinen konumlar gösterilir; boş harita göstermekten
    iyidir.
    """
    if kaynak not in UCAK_KAYNAKLARI:
        kaynak = KAYNAK_SIRA[0]

    g, b, k, d = bbox
    cok_genis = (abs(d - b) >= 60.0) or (abs(k - g) >= 30.0)

    if dunya or cok_genis:
        anlik = _cache_al("dunya_ucak", TTL_DUNYA, _dunya_anlik)
        if anlik:
            if not dunya:
                anlik = [a for a in anlik if g <= a["lat"] <= k and b <= a["lon"] <= d]
            gorulen = {}
            for a in anlik:
                u = _ucak_kisalt(a)
                if u and u["h"] and u["h"] not in gorulen:
                    gorulen[u["h"]] = u
            return {"kaynak": "opensky", "kapsam": "dünya", "kare": 1, "bayat": 0,
                    "eski": 0, "sayi": len(gorulen), "ucaklar": list(gorulen.values())}

    noktalar = _kareler(bbox)
    kullanilan = kaynak

    # --- 1) geniş görünüm: tek istek ---
    if len(noktalar) > 6 and not _kaynak_cezali("opensky"):
        anahtar = "kutu:%.2f:%.2f:%.2f:%.2f" % tuple(bbox)
        with _onbellek_kilit:
            kayit = _onbellek.get(anahtar)
        if kayit and time.time() - kayit[0] < TTL_UCAK_KARE:
            kutu_veri = list(kayit[1])
        else:
            kutu_veri = _opensky_kutu(bbox)
            if kutu_veri is not None:
                _cache_koy(anahtar, kutu_veri)
        if kutu_veri:
            gorulen = {}
            for a in kutu_veri:
                k = _ucak_kisalt(a)
                if k and k["h"] and k["h"] not in gorulen:
                    gorulen[k["h"]] = k
            return {"kaynak": "opensky", "kare": 1, "bayat": 0, "eski": 0,
                    "sayi": len(gorulen), "ucaklar": list(gorulen.values())}

    # --- 2) kare kare ---
    sonuc, bayat, eski_sayisi = [], [], 0
    for lat, lon in noktalar:
        # Anahtar kaynaktan bağımsız: hangi ağdan gelirse gelsin aynı kare.
        anahtar = "kare:%.2f:%.2f" % (lat, lon)
        with _onbellek_kilit:
            kayit = _onbellek.get(anahtar)
        if kayit and time.time() - kayit[0] < TTL_UCAK_KARE:
            sonuc.extend(kayit[1])
        else:
            bayat.append((anahtar, lat, lon, kayit[1] if kayit else None))

    if bayat:
        kullanilan = kaynak if not _kaynak_cezali(kaynak) else (
            "adsb.fi" if kaynak == "adsb.lol" else "adsb.lol")
        if _kaynak_cezali(kullanilan):
            # Kaynak sınırlı: istek atmayalım, son bilinen konumları göster.
            for (_a, _lt, _ln, eski) in bayat:
                if eski:
                    sonuc.extend(eski)
                    eski_sayisi += 1
        else:
            with ThreadPoolExecutor(max_workers=ES_ZAMANLI) as havuz:
                for (_a, lat, lon, eski), parca in zip(
                        bayat, havuz.map(lambda p: _kare_cek(kullanilan, p[1], p[2]), bayat)):
                    if parca is None:
                        if eski:
                            sonuc.extend(eski)
                            eski_sayisi += 1
                        continue
                    _cache_koy("kare:%.2f:%.2f" % (lat, lon), parca)
                    sonuc.extend(parca)

    gorulen = {}
    for a in sonuc:
        k = _ucak_kisalt(a)
        if k and k["h"] and k["h"] not in gorulen:
            gorulen[k["h"]] = k

    # Son güvence: kareler boş döndüyse (gönüllü ağ sınırlı) OpenSky'den
    # aynı kutuyu tek istekle sor. Panel boş kalmasın.
    if not gorulen and not _kaynak_cezali("opensky"):
        parca = _opensky_kutu(bbox)
        if parca:
            for a in parca:
                k = _ucak_kisalt(a)
                if k and k["h"] and k["h"] not in gorulen:
                    gorulen[k["h"]] = k
            if gorulen:
                return {"kaynak": "opensky", "kare": len(noktalar),
                        "bayat": len(bayat), "eski": eski_sayisi,
                        "sayi": len(gorulen), "ucaklar": list(gorulen.values())}

    return {"kaynak": kullanilan, "kare": len(noktalar), "bayat": len(bayat),
            "eski": eski_sayisi, "sayi": len(gorulen), "ucaklar": list(gorulen.values())}


# ----------------------------------------------------------------------------
# GEMİLER (AIS)
# ----------------------------------------------------------------------------
# Şu an Finlandiya/Baltık açık AIS akışı kullanılıyor: anahtarsız, canlı,
# gerçek veri. Dünya geneli için AISStream anahtarı gerekir; proje kökündeki
# ayar.json içine  {"aisstream_anahtar": "..."}  yazılınca o kaynak devreye
# alınacak. Anahtarsız yayında olduğunu gizlemiyoruz.

def gemiler():
    return _gemi_digitraffic()


def _gemi_digitraffic():
    veri = json_indir("https://meri.digitraffic.fi/api/ais/v1/locations", 40)
    ozellikler = veri.get("features") or []
    liste = []
    for f in ozellikler:
        c = (f.get("geometry") or {}).get("coordinates") or []
        p = f.get("properties") or {}
        if len(c) < 2:
            continue
        sog = p.get("sog")
        liste.append({
            "m": p.get("mmsi"),
            "la": round(c[1], 5),
            "lo": round(c[0], 5),
            "h": round(float(p.get("heading") or 0)),
            "y": round(float(p.get("cog") or 0), 1),
            "g": round(float(sog), 1) if isinstance(sog, (int, float)) else 0,
        })
    return {
        "kaynak": "Finlandiya açık AIS (meri.digitraffic.fi)",
        "kapsama": "Baltık ve Finlandiya kıyıları",
        "dunya_geneli": False,
        "not": "Dünya geneli gemi takibi için AISStream anahtarı gerekiyor",
        "sayi": len(liste),
        "gemiler": liste,
    }


# ----------------------------------------------------------------------------
# DEPREMLER  (USGS — kamu malı)
# ----------------------------------------------------------------------------

def depremler():
    ham = json_indir(
        "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson", 30)
    liste = []
    for f in ham.get("features", []):
        p = f.get("properties") or {}
        c = (f.get("geometry") or {}).get("coordinates") or []
        if len(c) < 2:
            continue
        liste.append({
            "la": round(c[1], 4), "lo": round(c[0], 4),
            "m": p.get("mag"), "yer": p.get("place"), "t": p.get("time"),
            "der": round(c[2], 1) if len(c) > 2 and c[2] is not None else None,
        })
    liste.sort(key=lambda d: d.get("m") or 0, reverse=True)
    return {"sayi": len(liste), "depremler": liste}


# ----------------------------------------------------------------------------
# YANGINLAR ve DOĞA OLAYLARI  (NASA EONET — açık, anahtarsız)
# ----------------------------------------------------------------------------

def _eonet():
    return json_indir(
        "https://eonet.gsfc.nasa.gov/api/v3/events?status=open&limit=400", 40)


def _eonet_liste(kategori=None, haric=None):
    ham = _eonet()
    liste = []
    for o in ham.get("events", []):
        katlar = [c.get("id") for c in (o.get("categories") or [])]
        ana = katlar[0] if katlar else "diger"
        if kategori and kategori not in katlar:
            continue
        if haric and ana in haric:
            continue
        for g in o.get("geometry") or []:
            if g.get("type") != "Point":
                continue
            koord = (g.get("coordinates") or [])[:2]
            if len(koord) < 2:
                continue
            liste.append({
                "ad": o.get("title"), "kat": ana,
                "la": round(koord[1], 4), "lo": round(koord[0], 4),
                "t": (g.get("date") or "")[:10],
                "bag": (o.get("sources") or [{}])[0].get("url"),
            })
    return liste


def yanginlar():
    liste = _eonet_liste("wildfires")
    return {"kaynak": "NASA EONET (açık veri)", "sayi": len(liste), "yanginlar": liste}


def olaylar():
    liste = _eonet_liste(None, haric={"wildfires"})
    return {"kaynak": "NASA EONET (açık veri)", "sayi": len(liste), "olaylar": liste}


# ----------------------------------------------------------------------------
# UYDULAR  (SatNOGS TLE + SGP4)
# ----------------------------------------------------------------------------

def _tle_listesi():
    ham = json_indir("https://db.satnogs.org/api/tle/?format=json", 120)
    liste = []
    for s in ham:
        t1, t2 = s.get("tle1"), s.get("tle2")
        if not t1 or not t2:
            continue
        ad = (s.get("tle0") or "").strip()
        if len(ad) > 2 and ad[1] == " ":
            ad = ad[2:]
        liste.append({"ad": ad.strip(), "n": s.get("norad_cat_id"),
                      "t1": t1, "t2": t2})
    return liste


def _gmst(jd):
    T = (jd - 2451545.0) / 36525.0
    return math.radians((280.46061837 + 360.98564736629 * (jd - 2451545.0)
                         + 0.000387933 * T * T - T * T * T / 38710000.0) % 360.0)


def uydular():
    from sgp4.api import Satrec, jday
    tleler = _cache_al("tle", TTL_TLE, _tle_listesi)

    lt = time.gmtime()
    jd, fr = jday(lt.tm_year, lt.tm_mon, lt.tm_mday,
                  lt.tm_hour, lt.tm_min, lt.tm_sec)
    g = _gmst(jd + fr)
    cg, sg = math.cos(g), math.sin(g)

    liste, hatali = [], 0
    for t in tleler:
        try:
            uydu = Satrec.twoline2rv(t["t1"], t["t2"])
            kod, r, _ = uydu.sgp4(jd, fr)
            if kod != 0:
                hatali += 1
                continue
            x, y, z = r
            xr = x * cg + y * sg
            yr = -x * sg + y * cg
            liste.append({
                "ad": t["ad"], "n": t["n"],
                "la": round(math.degrees(math.atan2(z, math.hypot(xr, yr))), 3),
                "lo": round(math.degrees(math.atan2(yr, xr)), 3),
                "i": round(math.hypot(x, y, z) - 6371.0),
            })
        except Exception:
            hatali += 1
    return {"kaynak": "SatNOGS TLE + SGP4", "sayi": len(liste),
            "hatali": hatali, "uydular": liste}


# ----------------------------------------------------------------------------
# DENİZALTI KABLOLARI  (submarinecablemap.com açık veri)
# ----------------------------------------------------------------------------

def kablolar():
    def uret():
        ham = json_indir(
            "https://www.submarinecablemap.com/api/v3/cable/cable-geo.json", 90)
        ince = []
        for f in ham.get("features", []):
            p = f.get("properties") or {}
            geom = f.get("geometry") or {}
            if geom.get("type") != "MultiLineString":
                continue
            hatlar = [[[round(c[0], 2), round(c[1], 2)] for c in hat]
                      for hat in (geom.get("coordinates") or []) if hat]
            if not hatlar:
                continue
            ince.append({"ad": p.get("name"),
                         "renk": p.get("color") or "#7f8c8d",
                         "hat": hatlar})
        return ince

    liste = _cache_al("kablo", TTL_KABLO,
                      lambda: diskten_json("kablolar.json", TTL_KABLO, uret))
    return {"kaynak": "submarinecablemap.com (açık veri)",
            "sayi": len(liste), "kablolar": liste}


# ----------------------------------------------------------------------------
# KAMERALAR  (Transport for London JamCams — resmî açık veri, anahtarsız)
# ----------------------------------------------------------------------------
# Türkiye için resmî ve açık bir trafik kamerası servisi bulunamadı: KGM ve
# belediyeler kamera görüntüsünü açık API olarak yayınlamıyor. Bu yüzden bu
# katman şu an yalnızca Londra'yı kapsıyor (890 kamera, canlı görüntü).
# Türkiye için şehir sitelerinden tek tek toplama işi ayrı bir çalışma.

def kameralar():
    def uret():
        ham = json_indir("https://api.tfl.gov.uk/Place/Type/JamCam", 60)
        liste = []
        for k in ham:
            ek = {p.get("key"): p.get("value")
                  for p in (k.get("additionalProperties") or [])}
            try:
                la, lo = float(k["lat"]), float(k["lon"])
            except (KeyError, TypeError, ValueError):
                continue
            liste.append({
                "ad": k.get("commonName"),
                "la": round(la, 5), "lo": round(lo, 5),
                "gorsel": ek.get("imageUrl"),
                "video": ek.get("videoUrl"),
            })
        return liste

    liste = _cache_al("kamera", 6 * 3600, uret)
    return {
        "kaynak": "Transport for London · JamCams (resmî açık veri)",
        "kapsama": "Londra",
        "dunya_geneli": False,
        "not": "Türkiye için resmî açık kamera servisi yok; eklenmesi ayrı çalışma",
        "sayi": len(liste),
        "kameralar": liste,
    }


# ----------------------------------------------------------------------------
# HAVALİMANLARI  (OurAirports — kamu malı)
# ----------------------------------------------------------------------------

def havalimanlari():
    yol = onbellek_yolu("airports.csv")
    taze = os.path.exists(yol) and (time.time() - os.path.getmtime(yol) < TTL_HAVA_DOSYA)
    if not taze:
        try:
            with open(yol, "wb") as f:
                f.write(indir("https://davidmegginson.github.io/ourairports-data/airports.csv", 120))
        except Exception:
            if not os.path.exists(yol):
                raise

    liste, tum = [], 0
    with open(yol, "r", encoding="utf-8", errors="replace", newline="") as f:
        for satir in csv.DictReader(f):
            tip = satir.get("type") or ""
            if tip.startswith("closed"):
                continue
            tum += 1
            if tip not in ("large_airport", "medium_airport"):
                continue
            try:
                la = float(satir["latitude_deg"])
                lo = float(satir["longitude_deg"])
            except (TypeError, ValueError):
                continue
            liste.append({
                "n": satir.get("name"), "la": round(la, 4), "lo": round(lo, 4),
                "t": "buyuk" if tip == "large_airport" else "orta",
                "i": (satir.get("iata_code") or "").strip() or None,
                "m": satir.get("municipality") or None,
                "u": satir.get("iso_country") or None,
            })
    return {"tum_sayi": tum, "sayi": len(liste), "havalimanlari": liste}


# ----------------------------------------------------------------------------
# YER ARAMA  (OpenStreetMap Nominatim)
# ----------------------------------------------------------------------------

def ara(sorgu):
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
        "q": sorgu, "format": "json", "limit": 6, "accept-language": "tr"})
    ham = json_indir(url, 20)
    return {"sonuclar": [{
        "ad": h.get("display_name"), "la": float(h["lat"]), "lo": float(h["lon"]),
        "tip": h.get("type"),
    } for h in ham if h.get("lat") and h.get("lon")]}


# ---------------------------------------------------------------------------
# ELEKTRİK SANTRALLERİ — WRI Global Power Plant Database (kamu malı, anahtarsız)
# ---------------------------------------------------------------------------
TTL_SANTRAL = 30 * 86400
SANTRAL_CSV = ("https://raw.githubusercontent.com/wri/global-power-plant-database"
               "/master/output_database/global_power_plant_database.csv")
YAKIT_TR = {
    "Solar": "Güneş", "Wind": "Rüzgâr", "Hydro": "Hidroelektrik", "Nuclear": "Nükleer",
    "Gas": "Doğal gaz", "Coal": "Kömür", "Oil": "Petrol", "Biomass": "Biyokütle",
    "Geothermal": "Jeotermal", "Waste": "Atık", "Petcoke": "Petrokok", "Cogeneration": "Kojenerasyon",
    "Storage": "Depolama", "Wave and Tidal": "Dalga/gelgit", "Other": "Diğer",
}


def santraller():
    def uret():
        ham = indir(SANTRAL_CSV, 240)
        satirlar = csv.DictReader(io.StringIO(ham.decode("utf-8", "replace")))
        yerler = []
        for s in satirlar:
            try:
                la, lo = float(s["latitude"]), float(s["longitude"])
                guc = float(s["capacity_mw"] or 0)
            except (ValueError, KeyError, TypeError):
                continue
            # NOT: eskiden 50 MW altı atılıyordu; argosun gösterdiği 34.936
            # sayısı WRI'nin tamamı. Filtre kaldırıldı, hepsi listelenir.
            yerler.append({
                "ad": (s["name"] or "").strip()[:60],
                "ulke": (s["country_long"] or s["country"] or "").strip()[:40],
                "yakit": YAKIT_TR.get((s["primary_fuel"] or "").strip(), (s["primary_fuel"] or "").strip()),
                "guc": round(guc, 1),
                "la": round(la, 4), "lo": round(lo, 4),
            })
        yerler.sort(key=lambda x: -x["guc"])
        return {"sayi": len(yerler), "liste": yerler[:40000]}
    return _cache_al("santral", TTL_SANTRAL, uret)


# ---------------------------------------------------------------------------
# GDACS — fırtına, sel, volkan, yangın, kuraklık (BM/EC, anahtarsız)
# ---------------------------------------------------------------------------
TTL_GDACS = 1800
GDACS_TIP = {"TC": "Tropikal fırtına", "FL": "Sel", "VO": "Volkan",
             "WF": "Orman yangını", "DR": "Kuraklık", "EQ": "Deprem"}


def gdacs():
    def uret():
        url = ("https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
               "?eventlist=TC;FL;VO;WF;DR")
        try:
            ham = json_indir(url, 40)
        except Exception:
            return {"sayi": 0, "liste": []}
        out = []
        for f in (ham.get("features") or []):
            p = f.get("properties") or {}
            ko = f.get("geometry") or {}
            c = ko.get("coordinates")
            if not c:
                continue
            if ko.get("type") == "Point":
                lo, la = c[0], c[1]
            else:
                en, boy = [], []
                for parca in (c if isinstance(c[0], list) else [c]):
                    for n in parca:
                        if isinstance(n, list) and len(n) >= 2:
                            boy.append(n[0]); en.append(n[1])
                if not en:
                    continue
                la, lo = sum(en) / len(en), sum(boy) / len(boy)
            tip = (p.get("eventtype") or "").upper()
            out.append({
                "tip": GDACS_TIP.get(tip, tip),
                "ad": (p.get("name") or p.get("description") or "")[:70],
                "seviye": (p.get("alertlevel") or "").lower(),
                "ulke": (p.get("country") or "")[:40],
                "tarih": (p.get("fromdate") or "")[:10],
                "la": round(float(la), 4), "lo": round(float(lo), 4),
            })
        return {"sayi": len(out), "liste": out}
    return _cache_al("gdacs", TTL_GDACS, uret)


# ---------------------------------------------------------------------------
# DENİZ BOĞAZLARI (sabit liste — dünya ticaretinin darboğazları)
# ---------------------------------------------------------------------------
BOGAZLAR = [
    ("Cebelitarık Boğazı", 35.96, -5.60, "Atlantik ↔ Akdeniz"), ("İstanbul Boğazı", 41.12, 29.05, "Karadeniz ↔ Marmara"),
    ("Çanakkale Boğazı", 40.20, 26.40, "Marmara ↔ Ege"), ("Süveyş Kanalı", 30.45, 32.35, "Kızıldeniz ↔ Akdeniz"),
    ("Babü'l-Mendeb", 12.58, 43.33, "Kızıldeniz ↔ Aden"), ("Hürmüz Boğazı", 26.57, 56.25, "Basra ↔ Umman"),
    ("Malakka Boğazı", 2.50, 101.50, "Hint ↔ Pasifik"), ("Singapur Boğazı", 1.22, 103.75, "Malakka çıkışı"),
    ("Panama Kanalı", 9.08, -79.68, "Atlantik ↔ Pasifik"), ("Kiel Kanalı", 54.30, 9.70, "Kuzey ↔ Baltık"),
    ("Dover Boğazı", 51.00, 1.40, "Manş ↔ Kuzey Denizi"), ("Tayvan Boğazı", 24.50, 119.50, "Doğu Çin ↔ Güney Çin"),
    ("Lombok Boğazı", -8.45, 115.75, "Hint ↔ Pasifik (Malakka yedeği)"),
    ("Sunda Boğazı", -5.95, 105.55, "Hint ↔ Cava"), ("Macellan Boğazı", -53.50, -70.50, "Atlantik ↔ Pasifik (güney)"),
    ("Bering Boğazı", 65.80, -169.00, "Pasifik ↔ Arktik"), ("Messina Boğazı", 38.20, 15.60, "Sicilya ↔ İtalya"),
    ("Korfu Boğazı", 39.70, 19.90, "Adriyatik çıkışı"), ("Hormuz dışı: Umman Körfezi", 24.50, 58.00, "Hürmüz çevresi"),
]


def bogazlar():
    return {"sayi": len(BOGAZLAR),
            "liste": [{"ad": a, "la": b, "lo": c, "not": d} for a, b, c, d in BOGAZLAR]}


# ---------------------------------------------------------------------------
# TAHMİN PİYASALARI — Manifold Markets (anahtarsız, açık API)
# ---------------------------------------------------------------------------
TTL_TAHMIN = 1800


def tahminler():
    def uret():
        try:
            ham = json_indir("https://api.manifold.markets/v0/markets?limit=300", 30)
        except Exception:
            return {"sayi": 0, "liste": []}
        out = []
        for m in (ham if isinstance(ham, list) else []):
            if m.get("outcomeType") != "BINARY" or m.get("isResolved"):
                continue
            olasilik = m.get("probability")
            if olasilik is None:
                continue
            la, lo = 0, 0
            if isinstance(m.get("locations"), list) and m["locations"]:
                try:
                    la, lo = float(m["locations"][0]["latitude"] or 0), float(m["locations"][0]["longitude"] or 0)
                except Exception:
                    la, lo = 0, 0
            out.append({
                "ad": (m.get("question") or "")[:90],
                "olasilik": round(float(olasilik) * 100, 1),
                "hacim": round(float(m.get("volume") or 0)),
                "url": m.get("url") or "",
                "la": la, "lo": lo,
            })
        out.sort(key=lambda x: -x["hacim"])
        return {"sayi": len(out), "liste": out[:400]}
    return _cache_al("tahmin", TTL_TAHMIN, uret)


# ---------------------------------------------------------------------------
# PİYASALAR — borsa, ETF, endeks, emtia, döviz, kripto
# ---------------------------------------------------------------------------
# Borsa/kripto: Finnhub (ayar.json içindeki finnhub_anahtar; ücretsiz plan).
# Endeks/emtia/döviz/ETF: Yahoo Finance chart ucu (anahtarsız).
# Her satırın bir konumu var: haritada o piyasanın şehrine iğnelenir.

TTL_PIYASA = 120

PIYASA_SEMBOLLERI = [
    # (gösterim, sembol, kaynak, enlem, boylam, şehir, tür)
    # --- endeksler ---
    ("S&P 500",        "^GSPC",       "yahoo",   40.7069,  -74.0113, "New York",    "endeks"),
    ("Dow Jones",      "^DJI",        "yahoo",   40.7069,  -74.0113, "New York",    "endeks"),
    ("Nasdaq",         "^IXIC",       "yahoo",   40.7069,  -74.0113, "New York",    "endeks"),
    ("Russell 2000",   "^RUT",        "yahoo",   40.7069,  -74.0113, "New York",    "endeks"),
    ("DAX",            "^GDAXI",      "yahoo",   50.1109,    8.6821, "Frankfurt",   "endeks"),
    ("CAC 40",         "^FCHI",       "yahoo",   48.8566,    2.3522, "Paris",       "endeks"),
    ("FTSE 100",       "^FTSE",       "yahoo",   51.5074,   -0.1278, "Londra",      "endeks"),
    ("IBEX 35",        "^IBEX",       "yahoo",   40.4168,   -3.7038, "Madrid",      "endeks"),
    ("AEX",            "^AEX",        "yahoo",   52.3676,    4.9041, "Amsterdam",   "endeks"),
    ("SMI",            "^SSMI",       "yahoo",   47.3769,    8.5417, "Zürih",       "endeks"),
    ("Nikkei 225",     "^N225",       "yahoo",   35.6762,  139.6503, "Tokyo",       "endeks"),
    ("Hang Seng",      "^HSI",        "yahoo",   22.3193,  114.1694, "Hong Kong",   "endeks"),
    ("Şanghay",        "000001.SS",   "yahoo",   31.2304,  121.4737, "Şanghay",     "endeks"),
    ("KOSPI",          "^KS11",       "yahoo",   37.5665,  126.9780, "Seul",        "endeks"),
    ("BSE Sensex",     "^BSESN",      "yahoo",   19.0760,   72.8777, "Mumbai",      "endeks"),
    ("Bovespa",        "^BVSP",       "yahoo",  -23.5505,  -46.6333, "São Paulo",   "endeks"),
    ("S&P/TSX",        "^GSPTSE",     "yahoo",   43.6532,  -79.3832, "Toronto",     "endeks"),
    ("ASX 200",        "^AXJO",       "yahoo",  -33.8688,  151.2093, "Sydney",      "endeks"),
    ("BIST 100",       "XU100.IS",    "yahoo",   41.0082,   28.9784, "İstanbul",    "endeks"),
    ("Tadawul",        "^TASI.SR",    "yahoo",   24.7136,   46.6753, "Riyad",       "endeks"),
    # --- emtia ---
    ("Brent petrol",   "BZ=F",        "yahoo",   51.5074,   -0.1278, "Londra",      "emtia"),
    ("WTI petrol",     "CL=F",        "yahoo",   40.7069,  -74.0113, "New York",    "emtia"),
    ("Altın (ons)",    "GC=F",        "yahoo",   40.7069,  -74.0113, "New York",    "emtia"),
    ("Gümüş (ons)",    "SI=F",        "yahoo",   40.7069,  -74.0113, "New York",    "emtia"),
    ("Bakır",          "HG=F",        "yahoo",   40.7069,  -74.0113, "New York",    "emtia"),
    ("Platin",         "PL=F",        "yahoo",   40.7069,  -74.0113, "New York",    "emtia"),
    ("Doğal gaz",      "NG=F",        "yahoo",   40.7069,  -74.0113, "New York",    "emtia"),
    ("Buğday",         "ZW=F",        "yahoo",   41.8781,  -87.6298, "Şikago",      "emtia"),
    ("Mısır",          "ZC=F",        "yahoo",   41.8781,  -87.6298, "Şikago",      "emtia"),
    ("Soya",           "ZS=F",        "yahoo",   41.8781,  -87.6298, "Şikago",      "emtia"),
    ("Kahve",          "KC=F",        "yahoo",   40.7069,  -74.0113, "New York",    "emtia"),
    ("Şeker",          "SB=F",        "yahoo",   40.7069,  -74.0113, "New York",    "emtia"),
    ("Pamuk",          "CT=F",        "yahoo",   40.7069,  -74.0113, "New York",    "emtia"),
    # --- döviz ---
    ("Euro/Dolar",     "EURUSD=X",    "yahoo",   50.1109,    8.6821, "Frankfurt",   "doviz"),
    ("Dolar/TL",       "USDTRY=X",    "yahoo",   41.0082,   28.9784, "İstanbul",    "doviz"),
    ("Euro/TL",        "EURTRY=X",    "yahoo",   41.0082,   28.9784, "İstanbul",    "doviz"),
    ("Sterlin/Dolar",  "GBPUSD=X",    "yahoo",   51.5074,   -0.1278, "Londra",      "doviz"),
    ("Dolar/Yen",      "USDJPY=X",    "yahoo",   35.6762,  139.6503, "Tokyo",       "doviz"),
    ("Dolar/Yuan",     "USDCNY=X",    "yahoo",   31.2304,  121.4737, "Şanghay",     "doviz"),
    ("Avustralya/Dolar", "AUDUSD=X",  "yahoo",  -33.8688,  151.2093, "Sydney",      "doviz"),
    ("Dolar/Frank",    "USDCHF=X",    "yahoo",   47.3769,    8.5417, "Zürih",       "doviz"),
    ("Dolar/Rupi",     "USDINR=X",    "yahoo",   19.0760,   72.8777, "Mumbai",      "doviz"),
    ("Dolar/Riyal",    "USDSAR=X",    "yahoo",   24.7136,   46.6753, "Riyad",       "doviz"),
    # --- kripto (Finnhub) ---
    ("Bitcoin",        "BINANCE:BTCUSDT", "finnhub", 40.7069, -74.0113, "New York", "kripto"),
    ("Ethereum",       "BINANCE:ETHUSDT", "finnhub", 40.7069, -74.0113, "New York", "kripto"),
    ("Solana",         "BINANCE:SOLUSDT", "finnhub", 40.7069, -74.0113, "New York", "kripto"),
    ("XRP",            "BINANCE:XRPUSDT", "finnhub", 40.7069, -74.0113, "New York", "kripto"),
    ("BNB",            "BINANCE:BNBUSDT", "finnhub", 40.7069, -74.0113, "New York", "kripto"),
    ("Dogecoin",       "BINANCE:DOGEUSDT", "finnhub", 40.7069, -74.0113, "New York", "kripto"),
    ("Cardano",        "BINANCE:ADAUSDT", "finnhub", 40.7069, -74.0113, "New York", "kripto"),
    # --- hisse (Finnhub, ABD) ---
    ("Apple",          "AAPL",        "finnhub", 37.3349, -122.0090, "Cupertino",   "hisse"),
    ("Microsoft",      "MSFT",        "finnhub", 47.6396, -122.1283, "Redmond",     "hisse"),
    ("Nvidia",         "NVDA",        "finnhub", 37.3704, -121.9636, "Santa Clara", "hisse"),
    ("Tesla",          "TSLA",        "finnhub", 30.2219,  -97.7625, "Austin",      "hisse"),
    ("Amazon",         "AMZN",        "finnhub", 47.6062, -122.3321, "Seattle",     "hisse"),
    ("Alphabet",       "GOOGL",       "finnhub", 37.4220, -122.0841, "Mountain View", "hisse"),
    ("Meta",           "META",        "finnhub", 37.4848, -122.1484, "Menlo Park",  "hisse"),
    ("Berkshire",      "BRK.B",       "finnhub", 41.2575,  -95.9783, "Omaha",       "hisse"),
    ("JPMorgan",       "JPM",         "finnhub", 40.7557,  -73.9754, "New York",    "hisse"),
    ("Visa",           "V",           "finnhub", 37.5585, -122.2743, "Foster City", "hisse"),
    ("Walmart",        "WMT",         "finnhub", 36.3729,  -94.2088, "Bentonville", "hisse"),
    ("ExxonMobil",     "XOM",         "finnhub", 32.7901,  -96.8020, "Irving",      "hisse"),
    ("Boeing",         "BA",          "finnhub", 38.9048,  -77.0510, "Arlington",   "hisse"),
    ("Intel",          "INTC",        "finnhub", 37.3875, -121.9636, "Santa Clara", "hisse"),
    ("Coca-Cola",      "KO",          "finnhub", 33.7490,  -84.3880, "Atlanta",     "hisse"),
    # --- hisse (Finnhub dışı, Yahoo) ---
    ("TSMC",           "TSM",         "yahoo",   25.0330,  121.5654, "Taipei",      "hisse"),
    ("ASML",           "ASML",        "yahoo",   51.4416,    5.4697, "Eindhoven",   "hisse"),
    ("Novo Nordisk",   "NVO",         "yahoo",   55.6761,   12.5683, "Kopenhag",    "hisse"),
    ("LVMH",           "MC.PA",       "yahoo",   48.8566,    2.3522, "Paris",       "hisse"),
    ("Toyota",         "7203.T",      "yahoo",   35.0824,  137.1560, "Toyota",      "hisse"),
    ("Samsung",        "005930.KS",   "yahoo",   37.5665,  126.9780, "Seul",        "hisse"),
    ("Türk Hava Yolları", "THYAO.IS", "yahoo",   41.0082,   28.9784, "İstanbul",    "hisse"),
    ("Aselsan",        "ASELS.IS",    "yahoo",   39.9334,   32.8597, "Ankara",      "hisse"),
    # --- ETF ---
    ("SPY (ETF)",      "SPY",         "yahoo",   40.7069,  -74.0113, "New York",    "etf"),
    ("QQQ (ETF)",      "QQQ",         "yahoo",   40.7069,  -74.0113, "New York",    "etf"),
    ("VIX korku endeksi", "^VIX",     "yahoo",   41.8781,  -87.6298, "Şikago",      "endeks"),
    ("Türkiye ETF",    "TUR",         "yahoo",   40.7069,  -74.0113, "New York",    "etf"),
    ("Altın ETF",      "GLD",         "yahoo",   40.7069,  -74.0113, "New York",    "etf"),
    ("Petrol ETF",     "USO",         "yahoo",   40.7069,  -74.0113, "New York",    "etf"),
]
PIYASA_TUR_TR = {"endeks": "Endeks", "emtia": "Emtia", "doviz": "Döviz",
                 "kripto": "Kripto", "hisse": "Hisse", "etf": "ETF"}


def _yahoo_fiyat(sembol):
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/"
           + urllib.parse.quote(sembol) + "?range=1d&interval=1d")
    veri = json_indir(url, 20)
    sonuc = ((veri.get("chart") or {}).get("result") or [None])[0]
    if not sonuc:
        return None, None
    m = sonuc.get("meta") or {}
    fiyat = m.get("regularMarketPrice")
    onceki = m.get("chartPreviousClose") or m.get("previousClose")
    return fiyat, onceki


def _finnhub_fiyat(sembol, anahtar):
    url = ("https://finnhub.io/api/v1/quote?symbol=" + urllib.parse.quote(sembol)
           + "&token=" + urllib.parse.quote(anahtar))
    d = json_indir(url, 20)
    f = d.get("c")
    if not f:
        return None, None
    return f, d.get("pc")


def piyasalar():
    anahtar = (ayar_oku() or {}).get("finnhub_anahtar") or ""

    def uret():
        liste = []

        def tek(satir):
            ad, sembol, kaynak, la, lo, sehir, tur = satir
            try:
                if kaynak == "finnhub":
                    if not anahtar:
                        return None
                    fiyat, onceki = _finnhub_fiyat(sembol, anahtar)
                else:
                    fiyat, onceki = _yahoo_fiyat(sembol)
            except Exception:
                return None
            if not fiyat:
                return None
            degisim = None
            if onceki:
                degisim = round((fiyat - onceki) / onceki * 100, 2)
            return {
                "ad": ad, "sembol": sembol, "tur": PIYASA_TUR_TR.get(tur, tur),
                "fiyat": round(float(fiyat), 2 if fiyat > 10 else 4),
                "degisim": degisim, "sehir": sehir,
                "la": la, "lo": lo, "kaynak": kaynak,
            }

        # 79 sembol tek tek sorulunca 25 sn sürüyordu; 4'lü havuzla ~7 sn.
        with ThreadPoolExecutor(max_workers=4) as havuz:
            for sonuc in havuz.map(tek, PIYASA_SEMBOLLERI):
                if sonuc:
                    liste.append(sonuc)
        return {"sayi": len(liste), "liste": liste,
                "not": "Finnhub ücretsiz plan + Yahoo Finance (anahtarsız)"}

    return _cache_al("piyasa", TTL_PIYASA, uret)


# ---------------------------------------------------------------------------
# HTTP işleyici
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# ARŞİV — geçmişe sarma (argosun PRO'da sattığı "hatırlar" işinin bedava hali)
# Arka plan iş parçacığı her ARSIV_ARALIK saniyede katmanların anlık
# görüntüsünü SQLite'a yazar; panel geçmişe sarınca buradan okur.
# ---------------------------------------------------------------------------
ARSIV_DB = os.path.join(PROJE, "veri", "arsiv.db")
ARSIV_ARALIK = 120          # saniye: anlık görüntü sıklığı
ARSIV_SAAT = 72             # kaç saatlik geçmiş saklanır
ARSIV_SINIR = 9000          # katman başına en fazla nokta
ARSIV_UC = {                # katman -> kendi ucumuz
    "ucak":   "/veri/ucak?dunya=1",
    "gemi":   "/veri/gemi",
    "deprem": "/veri/deprem",
    "yangin": "/veri/yangin",
    "olay":   "/veri/olay",
    "uydu":   "/veri/uydu",
}
ARSIV_ANAHTAR = {"ucak": "ucaklar", "gemi": "gemiler", "deprem": "depremler",
                 "yangin": "yanginlar", "olay": "olaylar", "uydu": "uydular"}
ARSIV_CADAVRA = 300         # uçak dünya anlık görüntüsü 15 dk'da yenilenir


def _arsiv_db():
    os.makedirs(os.path.dirname(ARSIV_DB), exist_ok=True)
    b = sqlite3.connect(ARSIV_DB, timeout=20)
    b.execute("PRAGMA journal_mode=WAL")
    b.execute("CREATE TABLE IF NOT EXISTS anlik("
              "zaman INTEGER NOT NULL, katman TEXT NOT NULL, sayi INTEGER,"
              "veri BLOB, PRIMARY KEY(zaman, katman))")
    return b


def arsiv_yaz(zaman, katman, liste):
    satir = []
    for x in liste[:ARSIV_SINIR]:
        try:
            la, lo = float(x.get("la")), float(x.get("lo"))
        except (TypeError, ValueError, AttributeError):
            continue
        et = x.get("ad") or x.get("c") or x.get("m") or ""
        satir.append([round(la, 3), round(lo, 3), str(et)[:28]])
    if not satir:
        return False
    ham = gzip.compress(json.dumps(satir, ensure_ascii=False,
                                   separators=(",", ":")).encode("utf-8"), 6)
    b = _arsiv_db()
    try:
        b.execute("INSERT OR REPLACE INTO anlik(zaman,katman,sayi,veri)"
                  " VALUES(?,?,?,?)", (zaman, katman, len(satir), ham))
        b.commit()
    finally:
        b.close()
    return True


def arsiv_saatler(katman, saat=ARSIV_SAAT):
    b = _arsiv_db()
    try:
        r = b.execute("SELECT zaman,sayi FROM anlik WHERE katman=? AND zaman>=?"
                      " ORDER BY zaman",
                      (katman, int(time.time()) - saat * 3600)).fetchall()
    finally:
        b.close()
    return [{"t": x[0], "sayi": x[1]} for x in r]


def arsiv_al(katman, zaman):
    b = _arsiv_db()
    try:
        r = b.execute("SELECT zaman,sayi,veri FROM anlik WHERE katman=?"
                      " ORDER BY ABS(zaman-?) LIMIT 1",
                      (katman, int(zaman))).fetchone()
    finally:
        b.close()
    if not r:
        return {"katman": katman, "t": None, "sayi": 0, "liste": [],
                "not": "bu katman için henüz kayıt yok"}
    return {"katman": katman, "t": r[0], "sayi": r[1],
            "liste": json.loads(gzip.decompress(r[2]).decode("utf-8"))}


def arsiv_iz(katman, ad, saat=72):
    """Bir aracın (uçak/gemi) arşivdeki izini çıkarır — 'uçağa tıkla, izini gör'."""
    b = _arsiv_db()
    try:
        satirlar = b.execute(
            "SELECT zaman,veri FROM anlik WHERE katman=? AND zaman>=? ORDER BY zaman",
            (katman, int(time.time()) - int(saat) * 3600)).fetchall()
    finally:
        b.close()
    hedef = str(ad).strip().lower()
    iz = []
    for zaman, blob in satirlar:
        try:
            kayitlar = json.loads(gzip.decompress(blob).decode("utf-8"))
        except Exception:
            continue
        for x in kayitlar:
            if str(x[2]).strip().lower() == hedef:
                iz.append([zaman, x[0], x[1]])
                break
    return {"katman": katman, "ad": ad, "nokta": len(iz), "iz": iz}


def arsiv_dongusu():
    """Arka planda katmanları diske yazar; sunucu kapanınca ölür (daemon)."""
    time.sleep(15)
    while True:
        try:
            simdi = int(time.time())
            for kat, uc in ARSIV_UC.items():
                try:
                    d = json_indir("http://127.0.0.1:%d%s" % (PORT, uc), 120)
                    liste = d.get(ARSIV_ANAHTAR[kat]) or []
                    if liste:
                        arsiv_yaz(simdi, kat, liste)
                except Exception:
                    pass
            b = _arsiv_db()
            try:
                b.execute("DELETE FROM anlik WHERE zaman < ?",
                          (int(time.time()) - ARSIV_SAAT * 3600,))
                b.commit()
            finally:
                b.close()
        except Exception:
            pass
        time.sleep(ARSIV_ARALIK)


# ---------------------------------------------------------------------------
# VIP & KURULUŞLAR — şirket merkezleri (Wikidata) + büyükelçilik ve askerî
# üsler (OpenStreetMap). Overpass dünya geneli sorgularda 3000 kayıtta
# kestiği için iş parçalarına bölünür ve arka planda kademeli toplanır;
# veri diske yazılır, panel toplandıkça büyüyen listeyi gösterir.
# ---------------------------------------------------------------------------
MERKEZ_DOSYA = os.path.join(PROJE, "veri", "merkez.json")
MERKEZ_TTL = 7 * 86400
MERKEZ_KUTULAR = [  # (ad, guney, bati, kuzey, dogu)
    ("Avrupa", 35, -12, 60, 45), ("Avrupa-kuzey", 54, -12, 72, 45),
    ("Asya-bati", 5, 45, 45, 100), ("Asya-dogu", -12, 95, 55, 180),
    ("Afrika", -36, -20, 37, 52), ("Kuzey Amerika", 14, -170, 72, -50),
    ("Latin Amerika", -56, -95, 15, -30), ("Okyanusya", -48, 110, 0, 180),
]

_WIKIDATA_SIRKET = """
SELECT ?cLabel ?ulkeLabel ?la ?lo WHERE {
  ?c wdt:P31/wdt:P279* wd:Q4830453 .
  ?c wdt:P159 ?hq . ?hq wdt:P625 ?coord .
  OPTIONAL { ?c wdt:P17 ?ulke }
  BIND(geof:latitude(?coord) AS ?la) BIND(geof:longitude(?coord) AS ?lo)
  SERVICE wikibase:label { bd:serviceParam wikibase:language "tr,en". }
} LIMIT 6000
"""


def _wikidata_sirketler():
    u = ("https://query.wikidata.org/sparql?format=json&query="
         + urllib.parse.quote(_WIKIDATA_SIRKET))
    d = json_indir(u, 90)
    cikti, gorulen = [], set()
    for s in d.get("results", {}).get("bindings", []):
        try:
            ad = s["cLabel"]["value"]
            if ad.startswith("Q") or ad in gorulen:
                continue
            gorulen.add(ad)
            cikti.append({"ad": ad[:70], "tip": "şirket merkezi",
                          "ulke": s.get("ulkeLabel", {}).get("value", "")[:40],
                          "la": round(float(s["la"]["value"]), 4),
                          "lo": round(float(s["lo"]["value"]), 4)})
        except (KeyError, ValueError):
            continue
    return cikti


OSM_UCLAR = [                       # Overpass aynaları: biri 429 verirse öteki
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass.osm.ch/api/interpreter",
]
MERKEZ_GUNLUK = os.path.join(PROJE, "veri", "merkez-gunluk.txt")


def _gunluk(yazi):
    try:
        os.makedirs(os.path.dirname(MERKEZ_GUNLUK), exist_ok=True)
        with open(MERKEZ_GUNLUK, "a", encoding="utf-8") as f:
            f.write("%s  %s\n" % (time.strftime("%d.%m %H:%M:%S"), yazi))
    except Exception:
        pass


def _osm_merkez(kutu, osm_sorgu):
    _, g, b, k, d = kutu          # kutu: (ad, güney, batı, kuzey, doğu)
    q = ("[out:json][timeout:120];%s(%s,%s,%s,%s);out center 3000;" %
         (osm_sorgu, g, b, k, d))
    son_hata = None
    for uc in OSM_UCLAR:
        try:
            d2 = json_indir(uc + "?data=" + urllib.parse.quote(q), 130)
            cikti = []
            for e in d2.get("elements", []):
                t = e.get("tags", {}) or {}
                tla = e.get("lat") or (e.get("center") or {}).get("lat")
                tlo = e.get("lon") or (e.get("center") or {}).get("lon")
                if tla is None or tlo is None:
                    continue
                cikti.append({"ad": (t.get("name") or t.get("name:tr") or "?")[:70],
                              "tip": t.get("_tip", "?"),
                              "ulke": (t.get("addr:country") or t.get("country") or "")[:40],
                              "la": round(float(tla), 4), "lo": round(float(tlo), 4)})
            return cikti
        except Exception as hata:
            son_hata = hata
            continue
    raise son_hata or RuntimeError("Overpass yanit vermedi")


def merkez_isle():
    """Tek tur: bir iş parçası indir, diske ekle. Arka plan döngüsü çağırır."""
    try:
        with open(MERKEZ_DOSYA, encoding="utf-8") as f:
            veri = json.load(f)
    except Exception:
        veri = {"liste": [], "bitti": [], "guncelleme": 0}
    if time.time() - veri.get("guncelleme", 0) > MERKEZ_TTL:
        veri = {"liste": [], "bitti": [], "guncelleme": int(time.time())}
    if len(veri["bitti"]) >= len(MERKEZ_KUTULAR) * 2 + 1:
        return len(veri["liste"])
    sira = len(veri["bitti"])
    try:
        if sira == 0:
            yeni = _wikidata_sirketler()
            et = "wikidata:sirket"
        else:
            kutu = MERKEZ_KUTULAR[(sira - 1) % len(MERKEZ_KUTULAR)]
            elcilik = (sira - 1) < len(MERKEZ_KUTULAR)
            # DİKKAT: OSM'de büyükelçilik artık "amenity=embassy" değil,
            # "diplomatic=embassy" olarak etiketleniyor. Yanlış etiketle
            # koca kutudan 3 kayıt geliyordu.
            yeni = _osm_merkez(kutu, 'nwr["diplomatic"="embassy"]["name"]' if elcilik
                               else 'nwr["military"="base"]["name"]')
            et = ("osm:elcilik:" if elcilik else "osm:us:") + kutu[0]
        # OSM sonuçlarında tip etiketini doldur
        tur = ("büyükelçilik" if "elcilik" in et else
               "askerî üs" if "us:" in et else None)
        if tur:
            for x in yeni:
                x["tip"] = tur
        veri["liste"].extend(yeni)
        veri["bitti"].append(et)
        veri["guncelleme"] = int(time.time())
        os.makedirs(os.path.dirname(MERKEZ_DOSYA), exist_ok=True)
        with open(MERKEZ_DOSYA, "w", encoding="utf-8") as f:
            json.dump(veri, f, ensure_ascii=False)
        _gunluk("OK  %-28s %5d kayit (toplam %d)" % (et, len(yeni), len(veri["liste"])))
        return len(veri["liste"])
    except Exception as hata:
        _gunluk("HATA %-27s %s: %s" % (et if 'et' in dir() else '?',
                                       type(hata).__name__, str(hata)[:70]))
        return len(veri["liste"])


def merkezler():
    try:
        with open(MERKEZ_DOSYA, encoding="utf-8") as f:
            veri = json.load(f)
    except Exception:
        veri = {"liste": [], "bitti": [], "guncelleme": 0}
    toplam = len(MERKEZ_KUTULAR) * 2 + 1
    sayim = {}
    for x in veri["liste"]:
        sayim[x["tip"]] = sayim.get(x["tip"], 0) + 1
    return {"sayi": len(veri["liste"]), "liste": veri["liste"][:40000],
            "tur_sayilari": sayim,
            "toplama": {"bitti": len(veri["bitti"]), "toplam": toplam},
            "bitti": len(veri["bitti"]) >= toplam,
            "kaynak": "Wikidata (şirket merkezleri) + OpenStreetMap (büyükelçilik, askerî üs)"}


def merkez_dongusu():
    time.sleep(40)
    while True:
        try:
            merkez_isle()
        except Exception:
            pass
        time.sleep(240)


# ---------------------------------------------------------------------------
# YENİ KATMANLAR (v0.12.0)
# hava · hava kirliliği · yağış radarı · deniz durumu · fay/levha hatları ·
# limanlar · volkanlar · tsunami uyarıları · uydu fotoğrafı · demiryolları ·
# uzaktan kumanda kuyruğu · yerel özet (Ollama)
# ---------------------------------------------------------------------------
TTL_HAVA_DURUM = 900
TTL_RADAR = 300
TTL_DENIZ = 1800
TTL_LEVHA = 30 * 86400
TTL_LIMAN = 30 * 86400
TTL_VOLKAN = 30 * 86400
TTL_TSUNAMI = 900
TTL_TREN = 86400
KUMANDA_DOSYA = os.path.join(PROJE, "veri", "kumanda.json")
KUMANDA_ESKI = 3600              # kuyrukta bu süreden eski komutlar temizlenir

DENIZ_NOKTA = [("İstanbul Boğazı", 41.10, 29.06), ("Marmara", 40.75, 28.20),
               ("İzmir Körfezi", 38.45, 27.10), ("Çeşme", 38.32, 26.30),
               ("Kuşadası", 37.85, 27.25), ("Bodrum", 37.03, 27.43),
               ("Marmaris", 36.85, 28.27), ("Fethiye", 36.62, 29.10),
               ("Antalya", 36.88, 30.70), ("Mersin", 36.80, 34.63),
               ("İskenderun", 36.58, 36.17), ("Samsun", 41.29, 36.33),
               ("Trabzon", 41.00, 39.72), ("Sinop", 42.03, 35.15),
               ("Zonguldak", 41.45, 31.79), ("Girne (KKTC)", 35.34, 33.32)]


def _il_merkezleri():
    """İl sınırları GeoJSON'undan il merkezlerini (ortalama nokta) üretir."""
    d = iller()
    cikti = []
    for x in d.get("iller") or []:
        noktalar = []

        def gez(o):
            if isinstance(o, (list, tuple)):
                if (len(o) >= 2 and isinstance(o[0], (int, float))
                        and isinstance(o[1], (int, float))):
                    noktalar.append((o[1], o[0]))
                else:
                    for p in o:
                        gez(p)
        gez(((x.get("geometry") or {}).get("coordinates")))
        if not noktalar:
            continue
        la = sum(p[0] for p in noktalar) / len(noktalar)
        lo = sum(p[1] for p in noktalar) / len(noktalar)
        cikti.append((x.get("ad") or "?", round(la, 4), round(lo, 4)))
    return cikti


def _openmeteo_seri(taban, alanlar, noktalar, ek=""):
    """Open-Meteo çok noktalı istek: 60'lık gruplar hâlinde sorar."""
    cikti = []
    for i in range(0, len(noktalar), 60):
        grup = noktalar[i:i + 60]
        la = ",".join(str(g[1]) for g in grup)
        lo = ",".join(str(g[2]) for g in grup)
        url = ("%s?latitude=%s&longitude=%s&current=%s%s"
               % (taban, la, lo, ",".join(alanlar), ek))
        d = json_indir(url, 35)
        d = d if isinstance(d, list) else [d]
        for kayit in d:
            cikti.append((kayit or {}).get("current") or {})
    return cikti


def hava_durum():
    def uret():
        merkez = _il_merkezleri()
        if not merkez:
            return {"kaynak": "Open-Meteo", "sayi": 0, "iller": []}
        seriler = _openmeteo_seri("https://api.open-meteo.com/v1/forecast",
                                  ["temperature_2m", "wind_speed_10m",
                                   "precipitation", "weather_code"],
                                  merkez, "&timezone=Europe/Istanbul")
        iller_ = []
        for (ad, la, lo), s in zip(merkez, seriler):
            iller_.append({"ad": ad, "la": la, "lo": lo,
                           "t": s.get("temperature_2m"), "r": s.get("wind_speed_10m"),
                           "y": s.get("precipitation"), "k": s.get("weather_code")})
        return {"kaynak": "Open-Meteo (açık veri)", "sayi": len(iller_), "iller": iller_}
    return _cache_al("hava_durum", TTL_HAVA_DURUM, uret)


def kirlilik():
    def uret():
        merkez = _il_merkezleri()
        if not merkez:
            return {"kaynak": "Open-Meteo", "sayi": 0, "iller": []}
        seriler = _openmeteo_seri("https://air-quality-api.open-meteo.com/v1/air-quality",
                                  ["pm2_5", "european_aqi"], merkez)
        iller_ = []
        for (ad, la, lo), s in zip(merkez, seriler):
            iller_.append({"ad": ad, "la": la, "lo": lo,
                           "pm": s.get("pm2_5"), "aqi": s.get("european_aqi")})
        return {"kaynak": "Open-Meteo hava kalitesi (açık veri)", "sayi": len(iller_),
                "iller": iller_}
    return _cache_al("kirlilik", TTL_HAVA_DURUM, uret)


def radar():
    def uret():
        d = json_indir("https://api.rainviewer.com/public/weather-maps.json", 25)
        host = d.get("host") or "https://tilecache.rainviewer.com"
        r = d.get("radar") or {}
        kareler = []
        for k in (r.get("past") or [])[-9:]:
            kareler.append({"t": k.get("time"), "gecmis": True,
                            "yol": "/v2/radar/%s/256/{z}/{x}/{y}/2/1_1.png" % k.get("time")})
        for k in (r.get("nowcast") or [])[:3]:
            kareler.append({"t": k.get("time"), "gecmis": False,
                            "yol": "/v2/radar/nowcast_%s/256/{z}/{x}/{y}/2/1_1.png" % k.get("time")})
        return {"kaynak": "RainViewer (açık)", "host": host, "sayi": len(kareler),
                "kareler": kareler, "guncelleme": int(time.time())}
    return _cache_al("radar", TTL_RADAR, uret)


def deniz():
    def uret():
        noktalar = [(a, la, lo) for a, la, lo in DENIZ_NOKTA]
        seriler = _openmeteo_seri("https://marine-api.open-meteo.com/v1/marine",
                                  ["wave_height", "wave_period",
                                   "sea_surface_temperature"], noktalar)
        cikti = []
        for (ad, la, lo), s in zip(noktalar, seriler):
            cikti.append({"ad": ad, "la": la, "lo": lo,
                          "d": s.get("wave_height"), "p": s.get("wave_period"),
                          "su": s.get("sea_surface_temperature")})
        return {"kaynak": "Open-Meteo deniz (açık veri)", "sayi": len(cikti), "noktalar": cikti}
    return _cache_al("deniz", TTL_DENIZ, uret)


def levhalar():
    def uret():
        d = diskten_json("levha-sinirlari.json", TTL_LEVHA, lambda: json_indir(
            "https://raw.githubusercontent.com/fraxen/tectonicplates/master/"
            "GeoJSON/PB2002_boundaries.json", 60))
        cizgiler = []
        for f in d.get("features") or []:
            g = f.get("geometry") or {}
            p = f.get("properties") or {}
            tip = g.get("type")
            if tip == "LineString":
                cizgiler.append({"ad": p.get("Name") or "levha",
                                 "k": [g.get("coordinates")]})
            elif tip == "MultiLineString":
                cizgiler.append({"ad": p.get("Name") or "levha",
                                 "k": g.get("coordinates")})
        return {"kaynak": "PB2002 levha sınırları (açık veri)", "sayi": len(cizgiler),
                "cizgiler": cizgiler}
    return _cache_al("levhalar", TTL_LEVHA, uret)


def faylar(kutu=None):
    """Diri fay hatları (GEM). 10 MB'lık dosya diskte tutulur, kutu ile süzülür."""
    def ham():
        return diskten_json("gem-faylar.json", TTL_LEVHA, lambda: json_indir(
            "https://raw.githubusercontent.com/GEMScienceTools/"
            "gem-global-active-faults/master/geojson/gem_active_faults_harmonized.geojson",
            180))

    d = ham()
    ozellikler = d.get("features") or []
    if kutu:
        b0, g0, b1, g1 = [float(x) for x in kutu]
        secili = []
        for f in ozellikler:
            g = (f.get("geometry") or {})
            koord = g.get("coordinates") or []
            if g.get("type") == "LineString":
                koord = [koord]
            for hat in koord:
                if not hat:
                    continue
                la = hat[0][1] if len(hat[0]) > 1 else 0
                lo = hat[0][0]
                if g0 <= la <= g1 and b0 <= lo <= b1:
                    secili.append({"k": [hat[::2]]})     # yarısını al (boyut)
                    break
        return {"kaynak": "GEM diri faylar (açık veri)", "sayi": len(secili),
                "cizgiler": secili, "kutu": kutu}
    cizgiler = []
    for f in ozellikler[:4000]:
        g = (f.get("geometry") or {})
        k = g.get("coordinates") or []
        if g.get("type") == "LineString":
            k = [k]
        cizgiler.append({"k": k})
    return {"kaynak": "GEM diri faylar (açık veri)", "sayi": len(cizgiler),
            "cizgiler": cizgiler}


def limanlar():
    def uret():
        sorgu = ("SELECT ?p ?pLabel ?loc WHERE { ?p wdt:P31 wd:Q44782; wdt:P625 ?loc . "
                 "SERVICE wikibase:label { bd:serviceParam wikibase:language \"tr,en\" } }")
        d = json_indir("https://query.wikidata.org/sparql?format=json&query="
                       + urllib.parse.quote(sorgu), 90)
        liste = []
        for b in ((d.get("results") or {}).get("bindings") or []):
            try:
                nokta = b["loc"]["value"]           # Point(lon lat)
                ic = nokta[nokta.find("(") + 1:nokta.find(")")].split()
                liste.append({"ad": (b.get("pLabel") or {}).get("value") or "Liman",
                              "lo": float(ic[0]), "la": float(ic[1])})
            except Exception:
                continue
        return {"kaynak": "Wikidata (açık veri)", "sayi": len(liste), "limanlar": liste}
    return diskten_json("limanlar.json", TTL_LIMAN, uret)


def volkanlar():
    def uret():
        sorgu = ("SELECT ?v ?vLabel ?loc WHERE { ?v wdt:P31 wd:Q8072; wdt:P625 ?loc . "
                 "SERVICE wikibase:label { bd:serviceParam wikibase:language \"tr,en\" } }")
        d = json_indir("https://query.wikidata.org/sparql?format=json&query="
                       + urllib.parse.quote(sorgu), 90)
        liste = []
        for b in ((d.get("results") or {}).get("bindings") or []):
            try:
                nokta = b["loc"]["value"]
                ic = nokta[nokta.find("(") + 1:nokta.find(")")].split()
                liste.append({"ad": (b.get("vLabel") or {}).get("value") or "Volkan",
                              "lo": float(ic[0]), "la": float(ic[1])})
            except Exception:
                continue
        return {"kaynak": "Wikidata (açık veri)", "sayi": len(liste), "volkanlar": liste}
    return diskten_json("volkanlar.json", TTL_VOLKAN, uret)


def tsunami():
    def uret():
        ham = indir("https://www.tsunami.gov/events/xml/PAAQAtom.xml", 30).decode("utf-8", "replace")
        kayitlar = []
        for blok in ham.split("<entry>")[1:]:
            def al(etiket):
                a = blok.find("<%s>" % etiket)
                b = blok.find("</%s>" % etiket)
                return blok[a + len(etiket) + 2:b].strip() if a >= 0 and b > a else ""
            baslik = al("title")
            tarih = al("updated")
            ozet = al("summary")
            kayitlar.append({"ad": baslik, "t": tarih, "ozet": ozet[:180]})
        return {"kaynak": "NOAA Tsunami Uyarı Merkezi (açık veri)", "sayi": len(kayitlar),
                "uyarilar": kayitlar[:12]}
    return _cache_al("tsunami", TTL_TSUNAMI, uret)


def uydu_foto(tarih=None):
    """NASA GIBS günlük uydu fotoğrafı (TrueColor) karo şablonu."""
    if not tarih:
        tarih = time.strftime("%Y-%m-%d", time.gmtime(time.time() - 2 * 86400))
    return {"kaynak": "NASA GIBS (açık veri)", "tarih": tarih,
            "katman": "MODIS_Terra_CorrectedReflectance_TrueColor",
            "sablon": ("https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/"
                       "MODIS_Terra_CorrectedReflectance_TrueColor/default/%s/"
                       "GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg" % tarih),
            "azami_zoom": 9}


def tren(kutu=None):
    """Demiryolu hatları (OpenStreetMap) — küçük kutular, aynalı Overpass."""
    if not kutu:
        kutu = [25.5, 35.5, 45.0, 42.5]           # Türkiye
    b0, g0, b1, g1 = [float(x) for x in kutu]

    def uret():
        q = ("[out:json][timeout:120];way[\"railway\"=\"rail\"](%s,%s,%s,%s);"
             "out geom 400;" % (g0, b0, g1, b1))
        son = None
        for uc in OSM_UCLAR if "OSM_UCLAR" in globals() else [
                "https://overpass-api.de/api/interpreter"]:
            try:
                d = json_indir(uc + "?data=" + urllib.parse.quote(q), 150)
                cizgiler = []
                for e in d.get("elements") or []:
                    geom = e.get("geometry") or []
                    if len(geom) < 2:
                        continue
                    cizgiler.append({"k": [[[p.get("lon"), p.get("lat")]
                                            for p in geom[::max(1, len(geom) // 60)]]]})
                return {"kaynak": "OpenStreetMap (açık veri)", "sayi": len(cizgiler),
                        "cizgiler": cizgiler[:400], "kutu": [b0, g0, b1, g1]}
            except Exception as hata:
                son = hata
                continue
        raise son or RuntimeError("Overpass yanıt vermedi")
    sonuc = None
    dosya_adi = "tren-%s.json" % ("_".join(str(round(x, 1)) for x in (b0, g0, b1, g1)))
    try:
        sonuc = diskten_json(dosya_adi, TTL_TREN, uret)
    except Exception:
        sonuc = None
    if sonuc and sonuc.get("sayi"):
        return sonuc
    # boş sonuç önbelleğe yazılmaz: kaynak yanıt vermediyse bir sonraki denemede tekrar sorulur
    if sonuc:
        return sonuc
    return {"kaynak": "OpenStreetMap", "sayi": 0, "cizgiler": [],
            "hata": "Overpass yanıt vermedi (yoğunluk sınırı)"}


# ---- uzaktan kumanda kuyruğu (telefon → panel) ----------------------------
def _kumanda_oku():
    try:
        with open(KUMANDA_DOSYA, "r", encoding="utf-8") as f:
            return json.load(f) or {"komutlar": []}
    except Exception:
        return {"komutlar": []}


def _kumanda_yaz(d):
    os.makedirs(os.path.dirname(KUMANDA_DOSYA), exist_ok=True)
    with open(KUMANDA_DOSYA, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)


def kumanda_ekle(komut, deger=None):
    d = _kumanda_oku()
    simdi = int(time.time())
    d["komutlar"] = [k for k in d.get("komutlar") or []
                     if simdi - (k.get("t") or 0) < KUMANDA_ESKI]
    # Komut numarası TEK YÖNLÜ artmalı. Kuyruk boşaldığında 1'e dönerse panel
    # "bu numarayı zaten gördüm" der ve yeni komutları sonsuza dek yok sayar.
    son_no = int(d.get("son_no") or 0)
    for k in d.get("komutlar") or []:
        son_no = max(son_no, int(k.get("no") or 0))
    yeni_no = son_no + 1
    d["son_no"] = yeni_no
    kayit = {"t": simdi, "no": yeni_no,
             "komut": str(komut)[:40], "deger": deger}
    d["komutlar"].append(kayit)
    if len(d["komutlar"]) > 30:
        del d["komutlar"][:-30]        # yalnız en yeni 30 komut tutulur
    d["son"] = simdi
    _kumanda_yaz(d)
    _gunluk("kumanda: %s (%s)" % (kayit["komut"], kayit["deger"]))
    return kayit


def kumanda_liste():
    d = _kumanda_oku()
    simdi = int(time.time())
    kalan = [k for k in d.get("komutlar") or []
             if simdi - (k.get("t") or 0) < KUMANDA_ESKI]
    if len(kalan) != len(d.get("komutlar") or []):
        d["komutlar"] = kalan
        _kumanda_yaz(d)
    return {"sayi": len(kalan), "komutlar": kalan}


def kumanda_temizle(no):
    """Panel komutları çalıştırdıktan sonra kuyruğu boşaltır (yeniden çalışmasın)."""
    d = _kumanda_oku()
    onceki = len(d.get("komutlar") or [])
    try:
        esik = int(no)
    except (TypeError, ValueError):
        esik = 0
    d["komutlar"] = [k for k in (d.get("komutlar") or []) if (k.get("no") or 0) > esik]
    _kumanda_yaz(d)
    return {"durum": "temizlendi", "silinen": onceki - len(d["komutlar"]),
            "kalan": len(d["komutlar"])}


def ozet():
    """Yerel Ollama varsa Türkçe özet üretir; yoksa açıkça söyler."""
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=4) as c:
            modeller = [m.get("name") for m in (json.loads(c.read().decode()).get("models") or [])]
    except Exception:
        return {"durum": "yok", "mesaj": "Yerel yapay zekâ (Ollama) çalışmıyor. "
                                        "Başlatmak için: ollama serve — model: ollama pull llama3.2"}
    if not modeller:
        return {"durum": "yok", "mesaj": "Ollama çalışıyor ama model yok (ollama pull llama3.2)"}
    return {"durum": "var", "modeller": modeller[:6],
            "mesaj": "Ollama hazır. Özet için paneldeki düğmeyi kullan."}


# ---------------------------------------------------------------------------
# UYARI MOTORU — panel açık olmasa da çalışır
# Bölgeler veri/uyarilar.json içinde tutulur; motor her UYARI_ARALIK saniyede
# katmanları tarar, bölgeye yeni giren olayı kuyruğa yazar ve (ayar.json'da
# webhook varsa) Discord/Telegram'a gönderir. Kuyruğu Hermes cron okuyabilir.
# ---------------------------------------------------------------------------
UYARI_DOSYA = os.path.join(PROJE, "veri", "uyarilar.json")
BILDIRIM_KUYRUK = os.path.join(PROJE, "veri", "bildirim-kuyrugu.jsonl")
UYARI_ARALIK = 120
# Gürültülü katmanlarda bölge başına bildirim aralığı (saniye).
# Uçak/gemi bir şehir kutusunda sürekli görünür; deprem/yangın/afet ise seyrektir.
UYARI_SESSIZ = {"ucak": 3600, "gemi": 3600,
                "deprem": 0, "yangin": 0, "olay": 0, "gdacs": 0}
UYARI_BILDIRIM_ILE = False       # sunucu doğrudan webhook göndermesin (köprü: bildirim.py)
UYARI_KATMANLAR = {
    "deprem": ("/veri/deprem", "depremler", "Deprem"),
    "yangin": ("/veri/yangin", "yanginlar", "Yangın"),
    "olay":   ("/veri/olay", "olaylar", "Doğa olayı"),
    "gemi":   ("/veri/gemi", "gemiler", "Gemi"),
    "ucak":   ("/veri/ucak?dunya=1", "ucaklar", "Uçak"),
    "gdacs":  ("/veri/gdacs", "liste", "Afet uyarısı"),
}


def uyari_oku():
    try:
        with open(UYARI_DOSYA, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def uyari_yaz(liste):
    os.makedirs(os.path.dirname(UYARI_DOSYA), exist_ok=True)
    with open(UYARI_DOSYA, "w", encoding="utf-8") as f:
        json.dump(liste, f, ensure_ascii=False)


def uyari_ekle(ad, kutu, katlar=None):
    liste = uyari_oku()
    kayit = {"ad": ad or ("Alan %d" % (len(liste) + 1)),
             "kutu": [float(x) for x in kutu],
             "katlar": katlar or ["deprem", "yangin", "olay", "gemi", "ucak", "gdacs"],
             "kurulus": int(time.time()), "gorulen": {}, "temel": 0, "olaylar": []}
    liste.append(kayit)
    uyari_yaz(liste)
    return kayit


def uyari_sil(indis):
    liste = uyari_oku()
    if 0 <= indis < len(liste):
        liste.pop(indis)
        uyari_yaz(liste)
    return len(liste)


def bildirim_gonder(metin):
    """ayar.json'da webhook varsa Discord/Telegram'a gönder (yoksa sessiz geç)."""
    ayar = ayar_oku()
    gonderildi = False
    try:
        wh = (ayar.get("discord_webhook") or "").strip()
        if wh:
            istek = urllib.request.Request(
                wh, data=json.dumps({"content": metin[:1900]}).encode("utf-8"),
                headers={"Content-Type": "application/json"})
            urllib.request.urlopen(istek, timeout=20).read()
            gonderildi = True
    except Exception as hata:
        _gunluk("webhook(discord) HATA %s" % str(hata)[:60])
    try:
        tok = (ayar.get("telegram_bot_token") or "").strip()
        cid = (ayar.get("telegram_chat_id") or "").strip()
        if tok and cid:
            u = ("https://api.telegram.org/bot%s/sendMessage?chat_id=%s&text=%s"
                 % (tok, cid, urllib.parse.quote(metin[:3500])))
            urllib.request.urlopen(u, timeout=20).read()
            gonderildi = True
    except Exception as hata:
        _gunluk("webhook(telegram) HATA %s" % str(hata)[:60])
    return gonderildi


def uyari_dongusu():
    time.sleep(35)
    while True:
        try:
            liste = uyari_oku()
            if liste:
                for kat, (uc, anahtar, etiket) in UYARI_KATMANLAR.items():
                    kullanan = [z for z in liste if kat in (z.get("katlar") or [])]
                    if not kullanan:
                        continue
                    try:
                        d = json_indir("http://127.0.0.1:%d%s" % (PORT, uc), 90)
                    except Exception:
                        continue
                    noktalar = d.get(anahtar) or []
                    for z in kullanan:
                        b0, b1, b2, b3 = z["kutu"]
                        for n in noktalar:
                            try:
                                la, lo = float(n.get("la")), float(n.get("lo"))
                            except (TypeError, ValueError):
                                continue
                            if not (b1 <= la <= b3 and b0 <= lo <= b2):
                                continue
                            ad = str(n.get("ad") or n.get("yer") or n.get("c") or "kayıt")[:80]
                            h = "%s|%s|%.2f%.2f" % (kat, ad, la, lo)
                            if z["gorulen"].get(h):
                                continue
                            z["gorulen"][h] = 1
                            if z.get("temel"):
                                bekle = UYARI_SESSIZ.get(kat, 0)
                                son = (z.get("son_gonderim") or {}).get(kat, 0)
                                if bekle and time.time() - son < bekle:
                                    continue          # sessizlik süresi: gürültü kesilir
                                z.setdefault("son_gonderim", {})[kat] = int(time.time())
                                satir = "%s: %s — %s (%.2f, %.2f)" % (
                                    etiket, ad, z["ad"], la, lo)
                                z.setdefault("olaylar", []).insert(
                                    0, {"t": int(time.time()), "kat": kat, "ad": ad,
                                        "la": la, "lo": lo})
                                del z["olaylar"][60:]
                                os.makedirs(os.path.dirname(BILDIRIM_KUYRUK), exist_ok=True)
                                with open(BILDIRIM_KUYRUK, "a", encoding="utf-8") as f:
                                    f.write(json.dumps(
                                        {"zaman": int(time.time()), "bolge": z["ad"],
                                         "katman": kat, "ad": ad, "la": la, "lo": lo,
                                         "gonderildi": False},
                                        ensure_ascii=False) + "\n")
                        # ilk tur taban çizgisidir
                        if not z.get("temel"):
                            z["temel"] = 1
                        anahtarlar = list(z["gorulen"].keys())
                        if len(anahtarlar) > 900:
                            for k in anahtarlar[:len(anahtarlar) - 900]:
                                z["gorulen"].pop(k, None)
                uyari_yaz(liste)
        except Exception:
            pass
        time.sleep(UYARI_ARALIK)


# ---------------------------------------------------------------------------
# TÜRKİYE İL SINIRLARI
# ---------------------------------------------------------------------------
TTL_IL = 30 * 86400
IL_KAYNAK = ("https://raw.githubusercontent.com/cihadturhan/tr-geojson/"
             "master/geo/tr-cities-utf8.json")


def iller():
    def uret():
        ham = indir(IL_KAYNAK, 90)
        d = json.loads(ham.decode("utf-8", "replace"))
        ozellikler = d.get("features") if isinstance(d, dict) else d
        cikti = []
        for f in ozellikler or []:
            p = f.get("properties", {}) or {}
            ad = p.get("name") or p.get("NAME") or p.get("il") or p.get("il_adi") or "?"
            g = f.get("geometry") or {}
            if g.get("type") not in ("Polygon", "MultiPolygon"):
                continue
            cikti.append({"ad": str(ad), "tip": "il", "geometry": g})
        return {"sayi": len(cikti), "iller": cikti,
                "kaynak": "cihadturhan/tr-geojson (kamuya açık)"}
    return _cache_al("iller", TTL_IL, uret)


# ---------------------------------------------------------------------------
# GÜNLÜK RAPOR
# ---------------------------------------------------------------------------
def rapor(_zorla=False):
    """Günlük durum raporu — 5 dakika önbelleklenir (düğme anında yanıt versin)."""
    global _RAPOR_ONBELLEK
    simdi = time.time()
    if not _zorla and _RAPOR_ONBELLEK and simdi - _RAPOR_ONBELLEK[0] < 300:
        return _RAPOR_ONBELLEK[1]
    cikti = _rapor_uret()
    _RAPOR_ONBELLEK = (simdi, cikti)
    return cikti


_RAPOR_ONBELLEK = None


def _rapor_uret():
    satirlar = ["USTAD GOZCU — GUNLUK DURUM RAPORU",
                time.strftime("%d.%m.%Y %H:%M"), ""]
    kalemler = [("Uçaklar (dünya)", "/veri/ucak?dunya=1", "ucaklar"),
                ("Gemiler", "/veri/gemi", "gemiler"),
                ("Uydular", "/veri/uydu", "uydular"),
                ("Depremler (24 saat)", "/veri/deprem", "depremler"),
                ("Yangınlar", "/veri/yangin", "yanginlar"),
                ("Doğa olayları", "/veri/olay", "olaylar"),
                ("Afet uyarıları", "/veri/gdacs", "liste"),
                ("Kameralar", "/veri/kamera", "kameralar"),
                ("Elektrik santralleri", "/veri/santral", "liste"),
                ("Havalimanları", "/veri/havalimani", "liste"),
                ("VIP & kuruluşlar", "/veri/merkez", "liste"),
                ("Piyasalar", "/veri/piyasa", "liste")]
    for ad, uc, anahtar in kalemler:
        try:
            d = json_indir("http://127.0.0.1:%d%s" % (PORT, uc), 90)
            sayi = d.get("sayi")
            if sayi is None:
                sayi = len(d.get(anahtar) or [])
            satirlar.append("  %-22s %s" % (ad, ("%d" % sayi).rjust(9)))
        except Exception:
            satirlar.append("  %-22s %s" % (ad, "veri yok".rjust(9)))

    # en büyük depremler + uyarı kayıtları
    try:
        d = json_indir("http://127.0.0.1:%d/veri/deprem" % PORT, 60)
        ds = sorted(d.get("depremler") or [], key=lambda x: -(x.get("m") or 0))[:5]
        if ds:
            satirlar.append("")
            satirlar.append("EN BÜYÜK DEPREMLER (24 saat):")
            for x in ds:
                satirlar.append("  M%.1f  %s" % (x.get("m") or 0, str(x.get("yer"))[:60]))
    except Exception:
        pass
    try:
        liste = uyari_oku()
        toplam = sum(len(z.get("olaylar") or []) for z in liste)
        satirlar.append("")
        satirlar.append("UYARI BÖLGESİ: %d bölge · %d kayıt" % (len(liste), toplam))
        for z in liste:
            for o in (z.get("olaylar") or [])[:3]:
                satirlar.append("  [%s] %s — %s" % (
                    z["ad"], o.get("ad"), time.strftime("%H:%M", time.localtime(o.get("t", 0)))))
    except Exception:
        pass
    satirlar += ["", "Kaynaklar: OpenSky · Digitraffic · USGS · NASA EONET · GDACS · WRI ·",
                 "OurAirports · TfL · Manifold · Wikidata · OpenStreetMap · Yahoo/Finnhub",
                 "Panel kendi bilgisayarinizda calisir; veri disariya gonderilmez."]
    return {"tarih": time.strftime("%d.%m.%Y %H:%M"), "metin": "\n".join(satirlar)}


# ---------------------------------------------------------------------------
# API LİSTESİ (kendi kendini belgeleyen uçlar)
# ---------------------------------------------------------------------------
API_LISTESI = [
    ("/saglik", "Sunucu durumu ve sürüm"),
    ("/veri/ucak?dunya=1", "Dünya uçak anlık görüntüsü (OpenSky)"),
    ("/veri/ucak?b=g,b,k,d", "Görünür kutu için uçaklar (adsb.lol / adsb.fi)"),
    ("/veri/gemi", "Gemiler (Finlandiya AIS, Baltık)"),
    ("/veri/uydu", "Uydular (CelesTrak + SGP4)"),
    ("/veri/deprem", "Depremler (USGS son 24 saat)"),
    ("/veri/yangin", "Yangınlar (NASA EONET)"),
    ("/veri/olay", "Doğa olayları (NASA EONET)"),
    ("/veri/gdacs", "Afet uyarıları (GDACS)"),
    ("/veri/havalimani", "Havalimanları (OurAirports)"),
    ("/veri/santral", "Elektrik santralleri (WRI)"),
    ("/veri/kablo", "Denizaltı kabloları (TeleGeography)"),
    ("/veri/bogaz", "Boğazlar ve kanallar"),
    ("/veri/kamera", "Trafik kameraları (TfL JamCams)"),
    ("/veri/tahmin", "Tahmin piyasaları (Manifold)"),
    ("/veri/piyasa", "Borsa/emtia/döviz/kripto kotasyonları"),
    ("/veri/merkez", "VIP & kuruluşlar (Wikidata + OSM)"),
    ("/veri/il", "Türkiye il sınırları (GeoJSON)"),
    ("/veri/arsiv/saatler?kat=ucak", "Arşivdeki anlık görüntü saatleri"),
    ("/veri/arsiv?kat=ucak&t=<unix>", "Belirli andaki katman görüntüsü"),
    ("/veri/hava", "81 il hava durumu (Open-Meteo)"),
    ("/veri/kirlilik", "81 il hava kirliliği PM2.5 + AQI"),
    ("/veri/radar", "Yağış radarı kareleri (RainViewer)"),
    ("/veri/deniz", "Kıyı noktaları deniz durumu (dalga, su sıcaklığı)"),
    ("/veri/levha", "Levha (tektonik) sınırları"),
    ("/veri/fay?b=g,b,k,d", "Diri fay hatları (kutu ile süzülür)"),
    ("/veri/liman", "Limanlar (Wikidata)"),
    ("/veri/volkan", "Volkanlar (Wikidata)"),
    ("/veri/tsunami", "Tsunami uyarıları (NOAA)"),
    ("/veri/uydu-foto?tarih=YYYY-AA-GG", "NASA GIBS uydu fotoğrafı karo şablonu"),
    ("/veri/tren?b=g,b,k,d", "Demiryolu hatları (OpenStreetMap)"),
    ("/veri/kumanda", "Telefon kumanda kuyruğu (GET okur, POST ekler)"),
    ("/veri/ozet", "Yerel yapay zekâ (Ollama) durumu"),
    ("/veri/uyari", "Uyarı bölgeleri ve kayıtlar (GET)"),
    ("/veri/rapor", "Günlük durum raporu (metin)"),
    ("/veri/ara?q=<metin>", "Yer/ülke arama (Nominatim)"),
    ("POST /veri/uyari", "Uyarı bölgesi ekle: {ad, kutu:[b0,b1,b2,b3]}"),
    ("POST /veri/uyari/sil", "Uyarı bölgesi sil: {indis}"),
]


class Isleyici(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=KOK, **kw)

    def log_message(self, bicim, *args):
        kod = str(args[1]) if len(args) > 1 else ""
        if kod.startswith(("4", "5")):
            sys.stderr.write("  ! %s\n" % (bicim % args))

    def _json(self, govde, kod=200):
        ham = json.dumps(govde, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        # Büyük yanıtları sıkıştır: santral listesi 2 MB'ı buluyor.
        sıkıstir = False
        try:
            kabul = (self.headers.get("Accept-Encoding") or "").lower()
            if len(ham) > 1200 and "gzip" in kabul:
                ham = gzip.compress(ham, 6)
                sıkıstir = True
        except Exception:
            pass
        try:
            self.send_response(kod)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(ham)))
            if sıkıstir:
                self.send_header("Content-Encoding", "gzip")
                self.send_header("Vary", "Accept-Encoding")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(ham)
        except (ConnectionAbortedError, BrokenPipeError):
            pass          # tarayıcı sekmeyi kapatmış, sorun değil

    def do_GET(self):
        ayrilan = urllib.parse.urlsplit(self.path)
        yol = ayrilan.path
        q = urllib.parse.parse_qs(ayrilan.query)

        try:
            if yol == "/saglik":
                return self._json({"durum": "calisiyor", "surum": SURUM,
                                   "saat": time.time()})

            if yol == "/veri/ucak":
                dunya = (q.get("dunya") or ["0"])[0] in ("1", "dogru", "true")
                bbox = (q.get("b") or [""])[0]
                if dunya and not bbox:
                    # giriş ekranı: bütün dünya, tek istek (sunucu içinde
                    # 15 dk önbelleklenir)
                    return self._json(ucaklar(KAYNAK_SIRA[0], (-89, -180, 89, 180), dunya=True))
                try:
                    g, b, k, d = [float(x) for x in bbox.split(",")]
                except ValueError:
                    return self._json({"hata": "b=guney,bati,kuzey,dogu gerekli"}, 400)
                kaynak = (q.get("kaynak") or [KAYNAK_SIRA[0]])[0]
                anahtar = "ucak:%s:%d:%d:%d:%d" % (
                    kaynak, round(g), round(b), round(k), round(d))
                return self._json(_cache_al(anahtar, 5,
                                            lambda: ucaklar(kaynak, (g, b, k, d))))

            if yol == "/veri/gemi":
                return self._json(_cache_al("gemi", TTL_GEMI, gemiler))
            if yol == "/veri/deprem":
                return self._json(_cache_al("deprem", TTL_DEPREM, depremler))
            if yol == "/veri/yangin":
                return self._json(_cache_al("yangin", TTL_EONET, yanginlar))
            if yol == "/veri/olay":
                return self._json(_cache_al("olay", TTL_EONET, olaylar))
            if yol == "/veri/uydu":
                return self._json(_cache_al("uydu", TTL_UYDU_KONUM, uydular))
            if yol == "/veri/kablo":
                return self._json(_cache_al("kablo_uc", TTL_KABLO, kablolar))
            if yol == "/veri/kamera":
                return self._json(_cache_al("kamera_uc", 6 * 3600, kameralar))
            if yol == "/veri/havalimani":
                return self._json(_cache_al("havalimani", TTL_HAVAALANI, havalimanlari))

            if yol == "/veri/santral":
                return self._json(santraller())
            if yol == "/veri/piyasa":
                return self._json(piyasalar())
            if yol == "/veri/gdacs":
                return self._json(gdacs())
            if yol == "/veri/bogaz":
                return self._json(bogazlar())
            if yol == "/veri/merkez":
                return self._json(merkezler())
            if yol == "/veri/tahmin":
                return self._json(tahminler())

            if yol == "/veri/arsiv/saatler":
                kat = (q.get("kat") or ["ucak"])[0]
                if kat not in ARSIV_UC:
                    return self._json({"hata": "bilinmeyen katman: " + kat}, 400)
                return self._json({"katman": kat, "aralik": ARSIV_ARALIK,
                                   "saat": ARSIV_SAAT, "saatler": arsiv_saatler(kat)})

            if yol == "/veri/arsiv":
                kat = (q.get("kat") or ["ucak"])[0]
                if kat not in ARSIV_UC:
                    return self._json({"hata": "bilinmeyen katman: " + kat}, 400)
                try:
                    t = int(float((q.get("t") or [time.time()])[0]))
                except ValueError:
                    return self._json({"hata": "t=saniye (unix) gerekli"}, 400)
                return self._json(arsiv_al(kat, t))

            if yol == "/veri/arsiv/iz":
                kat = (q.get("kat") or ["ucak"])[0]
                ad = (q.get("ad") or [""])[0]
                if kat not in ARSIV_UC or not ad:
                    return self._json({"hata": "kat ve ad gerekli"}, 400)
                saat = int((q.get("saat") or ["72"])[0])
                return self._json(arsiv_iz(kat, ad, saat))

            if yol == "/veri/hava":
                return self._json(hava_durum())
            if yol == "/veri/kirlilik":
                return self._json(kirlilik())
            if yol == "/veri/radar":
                return self._json(radar())
            if yol == "/veri/deniz":
                return self._json(deniz())
            if yol == "/veri/levha":
                return self._json(levhalar())
            if yol == "/veri/fay":
                kb = (q.get("b") or [""])[0]
                kutu = [float(x) for x in kb.split(",")] if len(kb.split(",")) == 4 else None
                return self._json(faylar(kutu))
            if yol == "/veri/liman":
                return self._json(limanlar())
            if yol == "/veri/volkan":
                return self._json(volkanlar())
            if yol == "/veri/tsunami":
                return self._json(tsunami())
            if yol == "/veri/uydu-foto":
                return self._json(uydu_foto((q.get("tarih") or [None])[0]))
            if yol == "/veri/tren":
                kb = (q.get("b") or [""])[0]
                kutu = [float(x) for x in kb.split(",")] if len(kb.split(",")) == 4 else None
                return self._json(tren(kutu))
            if yol == "/veri/kumanda":
                return self._json(kumanda_liste())
            if yol == "/veri/ozet":
                return self._json(ozet())

            if yol == "/api":
                return self._json({"surum": SURUM,
                                   "uclar": [{"yol": a, "aciklama": b}
                                             for a, b in API_LISTESI]})
            if yol == "/veri/il":
                return self._json(iller())
            if yol == "/veri/rapor":
                return self._json(rapor())
            if yol == "/veri/uyari":
                liste = uyari_oku()
                return self._json({"sayi": len(liste), "bolgeler": liste,
                                   "kuyruk": os.path.basename(BILDIRIM_KUYRUK)})

            if yol == "/veri/ara":
                s = (q.get("q") or [""])[0].strip()
                if not s:
                    return self._json({"sonuclar": []})
                return self._json(_cache_al("ara:" + s, TTL_ARAMA, lambda: ara(s)))

            if yol == "/veri/durum":
                return self._json({
                    "surum": SURUM,
                    "cezali_kaynaklar": list(_kaynak_ceza.keys()),
                    "onbellek_kayit": len(_onbellek),
                    "gomulu_kutuphane": os.path.isdir(KUTUPHANE),
                    "ayar_var": os.path.exists(AYAR_YOLU),
                })

            if yol.startswith("/veri/"):
                return self._json({"hata": "bilinmeyen uç: " + yol}, 404)

        except Exception as hata:
            return self._json({"hata": "%s: %s" % (type(hata).__name__, hata)}, 502)

        return super().do_GET()

    def do_POST(self):
        """Yalnız uyarı bölgesi ekleme/silme için (panel buradan yazar)."""
        ayrilan = urllib.parse.urlsplit(self.path)
        yol = ayrilan.path
        try:
            uzunluk = int(self.headers.get("Content-Length") or 0)
            ham = self.rfile.read(uzunluk) if uzunluk else b"{}"
            govde = json.loads(ham.decode("utf-8")) if ham else {}
        except Exception:
            govde = {}
        try:
            if yol == "/veri/uyari":
                kutu = govde.get("kutu") or []
                if len(kutu) != 4:
                    return self._json({"hata": "kutu=[b0,b1,b2,b3] gerekli"}, 400)
                kayit = uyari_ekle(govde.get("ad"), kutu, govde.get("katlar"))
                return self._json({"durum": "eklendi", "bolge": kayit,
                                   "sayi": len(uyari_oku())})
            if yol == "/veri/uyari/sil":
                kalan = uyari_sil(int(govde.get("indis", -1)))
                return self._json({"durum": "silindi", "sayi": kalan})
            if yol == "/veri/kumanda":
                kayit = kumanda_ekle(govde.get("komut"), govde.get("deger"))
                return self._json({"durum": "kuyruga eklendi", "kayit": kayit,
                                   "sayi": kumanda_liste()["sayi"]})
            if yol == "/veri/kumanda/temizle":
                return self._json(kumanda_temizle(govde.get("no")))
            return self._json({"hata": "bilinmeyen POST ucu: " + yol}, 404)
        except Exception as hata:
            return self._json({"hata": "%s: %s" % (type(hata).__name__, hata)}, 502)


class Sunucu(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, istek, adres):
        # bağlantı kopmaları konsolu kirletmesin
        hata = sys.exc_info()[1]
        if isinstance(hata, (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)):
            return
        super().handle_error(istek, adres)


# ----------------------------------------------------------------------------
# Başlatma
# ----------------------------------------------------------------------------

def bos_port_bul(ilk):
    for port in range(ilk, ilk + 20):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return ilk


def sgp4_hazir():
    try:
        import sgp4.api  # noqa: F401
        return True
    except Exception:
        return False


def main():
    global PORT
    if len(sys.argv) > 1:
        PORT = int(sys.argv[1])
    PORT = bos_port_bul(PORT)

    os.makedirs(ONBELLEK, exist_ok=True)
    adres = "http://127.0.0.1:%d" % PORT

    print("")
    print("  ==================================================")
    print("      U S T A D   G O Z C U    ~~~ o ~~~")
    print("          Gozcu hic kirpmaz.")
    print("  ==================================================")
    print("   Panel    : %s" % adres)
    print("   Klasor   : %s" % KOK)
    print("   Onbellek : %s" % ONBELLEK)
    print("   Uydu lib : %s" % ("gomulu sgp4 hazir" if sgp4_hazir()
                                else "YOK — uydu katmani calismaz"))
    print("   Kapat    : Ctrl + C")
    print("   Arsiv    : %d saat, %d sn'de bir (%s)" % (
        ARSIV_SAAT, ARSIV_ARALIK, os.path.basename(ARSIV_DB)))
    print("")

    threading.Thread(target=arsiv_dongusu, daemon=True).start()
    threading.Thread(target=merkez_dongusu, daemon=True).start()
    threading.Thread(target=uyari_dongusu, daemon=True).start()
    sunucu = Sunucu(("127.0.0.1", PORT), Isleyici)
    try:
        sunucu.serve_forever()
    except KeyboardInterrupt:
        print("\n  Gozcu nobeti birakti. Saglicakla.\n")
    finally:
        sunucu.server_close()


if __name__ == "__main__":
    main()
