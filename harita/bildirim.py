#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ÜSTAD GÖZCÜ — UYARI KÖPRÜSÜ
veri/bildirim-kuyrugu.jsonl içindeki gönderilmemiş kayıtları okur,
Türkçe özet üretir ve (varsa) webhook'a yollar.

Kullanım:
    python bildirim.py            → yeni uyarıları yazdırır (Hermes cron bunu teslim eder)
    python bildirim.py --hepsi    → son 20 uyarıyı (eski dahil) yazdırır
    python bildirim.py --test     → deneme mesajını webhook'a/ekrana gönderir

Webhook için PROJE/ayar.json içine şunlardan biri konur:
    {"discord_webhook": "https://discord.com/api/webhooks/..."}
    {"telegram_bot_token": "...", "telegram_chat_id": "..."}
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

KOK = os.path.dirname(os.path.abspath(__file__))
PROJE = os.path.dirname(KOK)
KUYRUK = os.path.join(PROJE, "veri", "bildirim-kuyrugu.jsonl")
AYAR = os.path.join(PROJE, "ayar.json")

KAT_AD = {"ucak": "Uçak", "gemi": "Gemi", "deprem": "Deprem", "yangin": "Yangın",
          "olay": "Doğa olayı", "gdacs": "Afet uyarısı"}


def ayar_oku():
    try:
        with open(AYAR, "r", encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def webhook_gonder(metin):
    """Discord / Telegram webhook'u varsa gönderir; gönderildiyse True döner."""
    a = ayar_oku()
    url = a.get("discord_webhook")
    if url:
        try:
            veri = json.dumps({"content": metin[:1900]}).encode("utf-8")
            istek = urllib.request.Request(url, data=veri, method="POST",
                                           headers={"Content-Type": "application/json"})
            urllib.request.urlopen(istek, timeout=20).read()
            return True
        except Exception:
            pass
    jeton, sohbet = a.get("telegram_bot_token"), a.get("telegram_chat_id")
    if jeton and sohbet:
        try:
            adres = "https://api.telegram.org/bot%s/sendMessage" % jeton
            veri = urllib.parse.urlencode({"chat_id": sohbet, "text": metin[:4000]}).encode()
            urllib.request.urlopen(adres, data=veri, timeout=20).read()
            return True
        except Exception:
            pass
    return False


def satir_yaz(kayit):
    kat = KAT_AD.get(kayit.get("katman"), kayit.get("katman") or "?")
    yer = ""
    if kayit.get("la") is not None and kayit.get("lo") is not None:
        yer = " (%.2f, %.2f)" % (kayit["la"], kayit["lo"])
    return "%s · %s · %s%s" % (kayit.get("bolge", "bölge"), kat,
                               kayit.get("ad") or "-", yer)


def main():
    hepsi = "--hepsi" in sys.argv
    test = "--test" in sys.argv
    if test:
        metin = "ÜSTAD GÖZCÜ — deneme bildirimi (%s)" % time.strftime("%d.%m.%Y %H:%M")
        ok = webhook_gonder(metin)
        print(metin + ("\n[webhook: gönderildi]" if ok else "\n[webhook: tanımlı değil — ayar.json'a ekleyin]"))
        return 0

    if not os.path.exists(KUYRUK):
        return 0
    kayitlar = []
    with open(KUYRUK, "r", encoding="utf-8") as f:
        for satir in f:
            satir = satir.strip()
            if not satir:
                continue
            try:
                kayitlar.append(json.loads(satir))
            except Exception:
                continue
    yeni = [k for k in kayitlar if not k.get("gonderildi")]
    if hepsi:
        yeni = kayitlar[-20:]
    if not yeni:
        return 0                     # sessiz çık: gürültü yapmaz

    baslik = "ÜSTAD GÖZCÜ — %d YENİ UYARI" % len(yeni)
    satirlar = [baslik, ""]
    for k in yeni[-12:]:
        satirlar.append("• " + satir_yaz(k))
    if len(yeni) > 12:
        satirlar.append("… ve %d kayıt daha" % (len(yeni) - 12))
    satirlar += ["", "Bölge yönetimi: panel → ⚠ / 📋"]
    metin = "\n".join(satirlar)
    ok = webhook_gonder(metin)

    if not ok:                       # webhook yoksa kuyruğu 'gönderildi' işaretle
        for k in kayitlar:
            if not k.get("gonderildi"):
                k["gonderildi"] = True
    else:
        for k in kayitlar:
            if not k.get("gonderildi") and k in yeni:
                k["gonderildi"] = True
    try:
        with open(KUYRUK, "w", encoding="utf-8") as f:
            for k in kayitlar[-400:]:
                f.write(json.dumps(k, ensure_ascii=False) + "\n")
    except Exception:
        pass

    if not ok:
        print(metin)                 # webhook yoksa Hermes cron teslim eder
    return 0


if __name__ == "__main__":
    sys.exit(main())
