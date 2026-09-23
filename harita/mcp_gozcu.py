#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ÜSTAD GÖZCÜ — MCP SUNUCUSU (stdio, JSON-RPC 2.0)

Hermes / Claude Desktop / herhangi bir MCP istemcisi bu betiği çalıştırıp
panel verisine araç (tool) üzerinden ulaşabilir. Sunucu (sunucu.py) açık olmalı.

Araçlar:
  gozcu_durum()                 → katman katman canlı sayılar
  gozcu_katman(katman, kutu?)   → bir katmanın ham kayıtları (kutu süzgeci)
  gozcu_rapor()                 → günlük durum raporu metni
  gozcu_uyari()                 → tanımlı uyarı bölgeleri + son olaylar
  gozcu_uyari_ekle(ad, kutu, katlar?)
  gozcu_uyari_sil(indis)

Hermes'e bağlama (config.yaml → mcp):
  mcp:
    servers:
      ustad-gozcu:
        command: python
        args: ["C:/Users/kenan/OneDrive/Desktop/USTAD-GOZCU/harita/mcp_gozcu.py"]
"""
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

PORT = 8811
TABAN = "http://127.0.0.1:%d" % PORT

ARACLAR = [
    {
        "name": "gozcu_durum",
        "description": "ÜSTAD GÖZCÜ panelindeki katmanların canlı kayıt sayılarını döndürür "
                       "(uçak, gemi, uydu, deprem, yangın, kamera, santral, piyasa...).",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "gozcu_katman",
        "description": "Bir katmanın ham kayıtlarını döndürür. katman: ucak|gemi|uydu|deprem|yangin|"
                       "olay|kablo|kamera|havalimani|santral|gdacs|bogaz|piyasa|merkez. "
                       "İsteğe bağlı kutu=[bati,guney,dogu,kuzey] ile alan süzülür.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "katman": {"type": "string"},
                "kutu": {"type": "array", "items": {"type": "number"}},
                "adet": {"type": "integer"},
            },
            "required": ["katman"],
        },
    },
    {
        "name": "gozcu_rapor",
        "description": "Günlük durum raporunu (katman sayıları, en büyük depremler, uyarılar) metin olarak döndürür.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "gozcu_uyari",
        "description": "Tanımlı uyarı (geofence) bölgelerini ve son yakalanan olayları döndürür.",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "gozcu_uyari_ekle",
        "description": "Yeni uyarı bölgesi ekler. kutu=[bati,guney,dogu,kuzey] (enlem/boylam derece). "
                       "katlar: deprem, yangin, olay, gemi, ucak, gdacs.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ad": {"type": "string"},
                "kutu": {"type": "array", "items": {"type": "number"}},
                "katlar": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["ad", "kutu"],
        },
    },
    {
        "name": "gozcu_uyari_sil",
        "description": "Uyarı bölgesini sırasına göre siler (gozcu_uyari çıktısındaki indis).",
        "inputSchema": {
            "type": "object",
            "properties": {"indis": {"type": "integer"}},
            "required": ["indis"],
        },
    },
]

UC = {"ucak": "/veri/ucak?dunya=1", "gemi": "/veri/gemi", "uydu": "/veri/uydu",
      "deprem": "/veri/deprem", "yangin": "/veri/yangin", "olay": "/veri/olay",
      "kablo": "/veri/kablo", "kamera": "/veri/kamera", "havalimani": "/veri/havalimani",
      "santral": "/veri/santral", "gdacs": "/veri/gdacs", "bogaz": "/veri/bogaz",
      "piyasa": "/veri/piyasa", "merkez": "/veri/merkez", "tahmin": "/veri/tahmin",
      "il": "/veri/il"}


def get(yol, sure=120):
    with urllib.request.urlopen(TABAN + yol, timeout=sure) as c:
        return json.loads(c.read().decode("utf-8", "replace"))


def post(yol, govde, sure=60):
    istek = urllib.request.Request(TABAN + yol, method="POST",
                                   data=json.dumps(govde).encode("utf-8"),
                                   headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(istek, timeout=sure) as c:
        return json.loads(c.read().decode("utf-8", "replace"))


def liste_al(d):
    for anahtar in ("ucaklar", "gemiler", "uydular", "depremler", "yanginlar", "olaylar",
                    "kablolar", "kameralar", "havalimanlari", "liste", "bogazlar",
                    "tahminler", "merkezler", "iller"):
        if isinstance(d.get(anahtar), list):
            return d[anahtar]
    return []


def araclar_calistir(ad, arg):
    if ad == "gozcu_durum":
        satirlar = []
        for anahtar, uc in UC.items():
            if anahtar == "tahmin":
                uc = "/veri/tahmin"
            try:
                d = get(uc, 90)
                n = d.get("sayi")
                if n is None:
                    n = len(liste_al(d))
                ek = ""
                if d.get("eski"):
                    ek = " (son bilinen)"
                satirlar.append("%-12s %s%s" % (anahtar, n, ek))
            except Exception as hata:
                satirlar.append("%-12s veri yok (%s)" % (anahtar, str(hata)[:40]))
        return "\n".join(satirlar)
    if ad == "gozcu_katman":
        kat = str(arg.get("katman", "")).lower()
        if kat not in UC:
            return "Bilinmeyen katman. Geçerli: " + ", ".join(sorted(UC))
        d = get(UC[kat])
        kayitlar = liste_al(d)
        kutu = arg.get("kutu")
        if kutu and len(kutu) == 4:
            b0, g0, b1, g1 = [float(x) for x in kutu]
            kayitlar = [k for k in kayitlar
                        if k.get("la") is not None and k.get("lo") is not None
                        and g0 <= float(k["la"]) <= g1 and b0 <= float(k["lo"]) <= b1]
        adet = int(arg.get("adet") or 25)
        return json.dumps({"katman": kat, "sayi": len(kayitlar),
                           "kayitlar": kayitlar[:adet]}, ensure_ascii=False, indent=1)
    if ad == "gozcu_rapor":
        d = get("/veri/rapor", 200)
        return d.get("metin", "") + "\n\n(rapor saati: %s)" % d.get("tarih", "?")
    if ad == "gozcu_uyari":
        d = get("/veri/uyari")
        satir = ["Tanımlı bölge: %d" % d.get("sayi", 0)]
        for i, z in enumerate(d.get("bolgeler") or []):
            satir.append("%d) %s — kutu=%s — katmanlar=%s — son olaylar:"
                         % (i, z.get("ad"), z.get("kutu"), z.get("katlar")))
            for o in (z.get("olaylar") or [])[:5]:
                satir.append("     · %s %s (%.2f, %.2f)"
                             % (o.get("kat"), o.get("ad"), o.get("la", 0), o.get("lo", 0)))
        return "\n".join(satir)
    if ad == "gozcu_uyari_ekle":
        d = post("/veri/uyari", {"ad": arg.get("ad"), "kutu": arg.get("kutu"),
                                 "katlar": arg.get("katlar")})
        return json.dumps(d, ensure_ascii=False)
    if ad == "gozcu_uyari_sil":
        d = post("/veri/uyari/sil", {"indis": int(arg.get("indis", -1))})
        return json.dumps(d, ensure_ascii=False)
    return "Bilinmeyen araç: " + ad


def cevap(gonder, kimlik, sonuc=None, hata=None):
    g = {"jsonrpc": "2.0", "id": kimlik}
    if hata is not None:
        g["error"] = hata
    else:
        g["result"] = sonuc
    sys.stdout.write(json.dumps(g, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    for satir in sys.stdin:
        satir = satir.strip()
        if not satir:
            continue
        try:
            istek = json.loads(satir)
        except Exception:
            continue
        yontem = istek.get("method")
        kimlik = istek.get("id")
        arg = istek.get("params") or {}
        if yontem == "initialize":
            cevap(None, kimlik, {"protocolVersion": "2024-11-05",
                                 "capabilities": {"tools": {}},
                                 "serverInfo": {"name": "ustad-gozcu", "version": "0.9.0"}})
        elif yontem == "notifications/initialized":
            continue
        elif yontem == "tools/list":
            cevap(None, kimlik, {"tools": ARACLAR})
        elif yontem == "tools/call":
            ad = arg.get("name")
            try:
                metin = araclar_calistir(ad, arg.get("arguments") or {})
                cevap(None, kimlik, {"content": [{"type": "text", "text": metin}]})
            except Exception as hata:
                cevap(None, kimlik, {"content": [{"type": "text",
                                                  "text": "Hata: %s" % hata}],
                                     "isError": True})
        elif kimlik is not None:
            cevap(None, kimlik, hata={"code": -32601, "message": "Bilinmeyen yöntem: %s" % yontem})
    return 0


if __name__ == "__main__":
    sys.exit(main())
