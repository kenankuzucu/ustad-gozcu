#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ÜSTAD GÖZCÜ — TÜM PROJE LİSTESİ (renkli Word)
=============================================
Projede ne varsa kalem kalem sıralar: düğmeler, katmanlar, sesli komutlar,
telefon kumandası, uyarı zinciri, arşiv, rapor, uçlar, dosyalar, zamanlanmış
işler, kaynaklar ve "neler aktif / neler bekliyor".

Kullanım:
    python gozcu-liste.py
Çıktı:
    Masaüstü\\USTAD-GOZCU-TUM-LISTE-<tarih>.docx
"""
import datetime
import json
import os
import sys
import urllib.request

KOK = "http://127.0.0.1:8811"
MASAUSTU = os.path.join(os.path.expanduser("~"), "OneDrive", "Desktop")
if not os.path.isdir(MASAUSTU):
    MASAUSTU = os.path.join(os.path.expanduser("~"), "Desktop")
PROJE = r"C:\Users\kenan\OneDrive\Desktop\USTAD-GOZCU"
MADALYON = os.path.join(PROJE, "harita", "foto", "ustad-kenan.png")

TEAL, AMBER, RED, BLUE, MOR, GRI = "2BF0C8", "FFD23B", "FF3B4D", "3D8BFF", "A98BFF", "6B7C86"


def al(yol, sure=30):
    with urllib.request.urlopen(KOK + yol, timeout=sure) as c:
        return json.loads(c.read().decode("utf-8", "replace"))


def canli_sayilar():
    """Katman sayılarını canlı uçlardan çeker; olmayanı '—' bırakır."""
    uclar = {
        "uçak (dünya)": ("/veri/ucak?dunya=1", "sayi"),
        "gemi": ("/veri/gemi", "sayi"),
        "uydu": ("/veri/uydu", "sayi"),
        "deprem": ("/veri/deprem", "sayi"),
        "yangın": ("/veri/yangin", "sayi"),
        "doğa olayı": ("/veri/olay", "sayi"),
        "havalimanı": ("/veri/havalimani", "sayi"),
        "denizaltı kablosu": ("/veri/kablo", "sayi"),
        "kamera": ("/veri/kamera", "sayi"),
        "santral": ("/veri/santral", "sayi"),
        "GDACS afet": ("/veri/gdacs", "sayi"),
        "boğaz": ("/veri/bogaz", "sayi"),
        "tahmin piyasası": ("/veri/tahmin", "sayi"),
        "piyasa": ("/veri/piyasa", "sayi"),
        "VIP & kuruluş": ("/veri/merkez", "sayi"),
        "Türkiye il sınırı": ("/veri/il", "sayi"),
        "hava (il)": ("/veri/hava", "sayi"),
        "hava kirliliği (il)": ("/veri/kirlilik", "sayi"),
        "deniz durumu (nokta)": ("/veri/deniz", "sayi"),
        "liman": ("/veri/liman", "sayi"),
        "volkan": ("/veri/volkan", "sayi"),
        "levha çizgisi": ("/veri/levha", "sayi"),
        "diri fay (TR)": ("/veri/fay?b=25.5,35.5,45,42.5", "sayi"),
        "yağış radarı karesi": ("/veri/radar", "sayi"),
        "tsunami kaydı": ("/veri/tsunami", "sayi"),
    }
    cikti = []
    for ad, (yol, alan) in uclar.items():
        try:
            d = al(yol, 60)
            cikti.append((ad, str(d.get(alan, "—"))))
        except Exception:
            cikti.append((ad, "— (şu an yanıt yok)"))
    return cikti


def surum(doc, baslik, renk):
    from docx.shared import Pt, RGBColor
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
    t = doc.add_table(rows=1, cols=1)
    t.style = "Table Grid"
    h = t.rows[0].cells[0]
    h.text = ""
    k = h.paragraphs[0].add_run("  " + baslik)
    k.bold = True
    k.font.size = Pt(13)
    k.font.color.rgb = RGBColor.from_string("FFFFFF")
    golge = OxmlElement("w:shd")
    golge.set(qn("w:fill"), renk)
    h._tc.get_or_add_tcPr().append(golge)
    doc.add_paragraph()
    return t


def tablo(doc, basliklar, satirlar, genislikler=None):
    from docx.shared import Pt
    t = doc.add_table(rows=1, cols=len(basliklar))
    t.style = "Table Grid"
    for i, b in enumerate(basliklar):
        c = t.rows[0].cells[i]
        c.text = ""
        k = c.paragraphs[0].add_run(b)
        k.bold = True
        k.font.size = Pt(10)
    for s in satirlar:
        hc = t.add_row().cells
        for i, x in enumerate(s):
            hc[i].text = ""
            hc[i].paragraphs[0].add_run(str(x)).font.size = Pt(9.5)
    return t


def madde(doc, metin, kalin=False, renk=None, boyut=10.5):
    from docx.shared import Pt, RGBColor
    p = doc.add_paragraph(style="List Bullet")
    k = p.add_run(metin)
    k.font.size = Pt(boyut)
    k.bold = kalin
    if renk:
        k.font.color.rgb = RGBColor.from_string(renk)
    return p


def uret():
    from docx import Document
    from docx.shared import Pt, RGBColor, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    simdi = datetime.datetime.now()
    doc = Document()
    for b in doc.sections:
        b.left_margin = Cm(2.0)
        b.right_margin = Cm(2.0)

    # ---------------- KAPAK ----------------
    if os.path.isfile(MADALYON):
        try:
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.add_run().add_picture(MADALYON, width=Cm(3.4))
        except Exception:
            pass
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    k = p.add_run("ÜSTAD GÖZCÜ")
    k.bold = True
    k.font.size = Pt(34)
    k.font.color.rgb = RGBColor.from_string(TEAL)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    k = p.add_run("TÜM PROJE LİSTESİ — NE VAR, NE AKTİF")
    k.bold = True
    k.font.size = Pt(14)
    k.font.color.rgb = RGBColor.from_string(AMBER)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    k = p.add_run(simdi.strftime("%d.%m.%Y · %H:%M") + " · ÜSTAD KENAN KUZUCU")
    k.font.size = Pt(11)
    k.font.color.rgb = RGBColor.from_string(GRI)
    doc.add_paragraph()

    surum(doc, "SÜRÜM:" + son_surum(), TEAL)

    # ---------------- 1. SÜRÜM GEÇMİŞİ ----------------
    surum(doc, "1. SÜRÜM GEÇMİŞİ — NE ZAMAN NE EKLENDİ", TEAL)
    tablo(doc, ["Sürüm", "Eklenen"], [
        ["v0.5", "Arşiv motoru (72 saat), uyarı bölgesi, dışa aktarma (CSV/KML/GeoJSON), "
                 "video duvarı, TV modu, ilk 16 araç düğmesi"],
        ["v0.7", "HAREKÂT ODASI (askerî şûra görünümü): radar, blip, sayaç panoları, "
                 "akan yazı bandı, 16 bölgeli seyir"],
        ["v0.8", "Uyarı motoru sunucuda (panel kapalıyken de tarar), bildirim kuyruğu, "
                 "WhatsApp köprüsü (Hermes işi, 10 dk), arşiv izi ucu"],
        ["v0.9", "Sesli anons, uçak/gemi izi, deprem dalgası, ekran koruyucu, günlük rapor, "
                 "KML içe aktarma, 81 il sınırı, TV'de 3D eğim, MCP sunucusu (6 araç)"],
        ["v0.10", "CANLI UÇAK HAREKETİ — ölü hesap (hız/yön ile 200 ms'de ilerletme)"],
        ["v0.11", "Canlı GEMİ hareketi + sinematik açılış perdesi ve günün sözü"],
        ["v0.12", "8 yeni katman (hava, kirlilik, deniz, liman, volkan, levha, fay, tren), "
                  "yağış radarı, uydu fotoğrafı (tarihli), uçak iz kuyruğu, uçak etiketleri, "
                  "irtifa süzgeci, katman kumanda paneli"],
        ["v0.13", "Zaman makinesi (arşivi film gibi oynat), telefondan kumanda, olay→bildirim "
                  "zinciri (kırmızı halka + anons), sesli günlük özet, 2. ekran, harekât "
                  "odasında canlı olay akışı, günlük Word raporu + zamanlama"],
        ["v0.14", "SESLE HER ŞEY: 64 hedefe (26 düğme + tüm katmanlar + bölgeler) sesli komut, "
                  "Türkçe harf duyarsız eşleştirme, toplu komut, komut listesi penceresi"],
    ])
    doc.add_paragraph()

    # ---------------- 2. ARAÇ DÜĞMELERİ ----------------
    surum(doc, "2. SOL ALT ARAÇ DÜĞMELERİ (" + str(len(DUGMELER)) + " DÜĞME)", BLUE)
    satirlar = [[str(i + 1), d["ad"]] for i, d in enumerate(DUGMELER)]
    tablo(doc, ["No", "Görevi"], satirlar)
    doc.add_paragraph()

    # ---------------- 3. KATMANLAR ----------------
    surum(doc, "3. HARİTA KATMANLARI — CANLI SAYILAR", AMBER)
    tablo(doc, ["Katman", "Kayıt"], canli_sayilar())
    doc.add_paragraph()

    # ---------------- 4. SESLİ KOMUT ----------------
    surum(doc, "4. SESLİ KOMUT SİSTEMİ (v0.14)", MOR)
    madde(doc, "Mikrofon düğmesi 🎤 → dinler; anlaşılan komut ekranda yazılır.", True)
    madde(doc, "Hedef sayısı: " + str(SES_HEDEF) + " (26 araç düğmesi + tüm harita katmanları "
               "+ 8 yeni katman + 4 tema + 18 bölge + katman paneli satırları).")
    madde(doc, "Çoklu komut: \"uçakları kapat ve gemileri aç\" · \"radar, etiket aç\"")
    madde(doc, "Telefondan serbest Türkçe komut: kumanda.html üstündeki kutuya yaz ya da "
               "klavye mikrofonuyla söyle → panele gönderilir.")
    madde(doc, "Türkçe harf duyarsız: 'harekat odasi' yazsan da 'harekât odası' anlar.")
    madde(doc, "Örnekler:")
    for o in ['"uçakları kapat" · "gemileri aç" · "depremi kapat" · "kameraları aç"',
              '"hava durumunu aç" · "limanları aç" · "volkanları aç"',
              '"radar aç" · "yağış radarını kapat" · "iz kuyruğunu aç" · "etiketleri aç"',
              '"harekât odasını aç" · "video duvarını aç" · "tv modu" · "zaman makinesini aç"',
              '"baltığa git" · "akdenize git" · "gaziantebe git" · "gemi bölgesi" (gemiler de açılır)',
              '"mor tema" · "buz tema" · "hepsini kapat" · "hepsini aç" · "temizle"',
              '"neler yapabilirsin" → tüm komut listesi ekranda']:
        madde(doc, o, renk=GRI)
    madde(doc, "Ayrıca: her komut sesli onaylanır (Türkçe anons) ve ekranda yazılır.")
    doc.add_paragraph()

    # ---------------- 5. TELEFON KUMANDASI ----------------
    surum(doc, "5. TELEFONDAN KUMANDA (kumanda.html)", BLUE)
    madde(doc, "Telefondan aynı ağdaki panele bağlanılır: " + KOK + "/kumanda.html", True)
    madde(doc, "39 düğme: görünüm, katmanlar, yeni katmanlar, bölgeler, ses ve diğer.")
    madde(doc, "Komut sunucuya yazılır, panel 2,5 saniyede bir okuyup uygular.")
    madde(doc, "Kuyruk tüketimlidir: çalıştırılan komut silinir, 2 dakikadan eski komut oynamaz.")
    doc.add_paragraph()

    # ---------------- 6. UYARI ZİNCİRİ ----------------
    surum(doc, "6. UYARI / BİLDİRİM ZİNCİRİ", RED)
    madde(doc, "Uyarı motoru sunucuda çalışır (panel kapalıyken de) — 120 saniyede bir tarar.")
    madde(doc, "Bölgeye düşen yeni olay: WhatsApp mesajı (Hermes işi, 10 dk) +")
    madde(doc, "panelde kırmızı yayılan halka + Türkçe sesli anons + harekât odası akışına satır.")
    madde(doc, "İzlenen katmanlar: deprem, yangın, doğa olayı, GDACS, uçak, gemi (gürültü süzgeçli).")
    doc.add_paragraph()

    # ---------------- 7. ARŞİV / RAPOR / MCP ----------------
    surum(doc, "7. ARŞİV · ZAMAN MAKİNESİ · RAPOR · MCP", TEAL)
    madde(doc, "Arşiv: SQLite + gzip, 72 saat, 2 dakikada bir, 6 katman.")
    madde(doc, "Zaman makinesi: arşivi film gibi oynatır (1–72 saat, en fazla ~70 kare).")
    madde(doc, "Günlük rapor: renkli Word — Masaüstü\\USTAD-GOZCU-RAPOR-<tarih>.docx")
    madde(doc, "MCP sunucusu: 6 araç (durum, katman, rapor, uyarı, uyarı ekle, uyarı sil) — "
               "Hermes sohbetinden panele komut verilebilir.")
    doc.add_paragraph()

    # ---------------- 8. UÇLAR ----------------
    surum(doc, "8. SUNUCU UÇLARI (" + str(len(UCLAR)) + " ADET, port 8811)", GRI)
    tablo(doc, ["Yol", "Ne verir"], [[u.get("yol", ""), u.get("aciklama", "")] for u in UCLAR])
    doc.add_paragraph()

    # ---------------- 9. DOSYALAR ----------------
    surum(doc, "9. DOSYA YAPISI", BLUE)
    for s, ac in [
        ("harita\\index.html", "HARİTA + 7 ek script bloğu (v0.5 → v0.14)"),
        ("harita\\giris.html", "GİRİŞ EKRANI (kayan şerit, 14 katman)"),
        ("harita\\kumanda.html", "TELEFON KUMANDASI (39 düğme)"),
        ("harita\\sunucu.py", "Yerel köprü sunucusu (38 uç, arka plan döngüleri)"),
        ("harita\\bildirim.py", "Uyarı köprüsü (kuyruk → WhatsApp)"),
        ("harita\\mcp_gozcu.py", "MCP sunucusu (6 araç)"),
        ("harita\\gozcu-rapor.py", "Günlük renkli Word raporu"),
        ("harita\\ayar.json", "Yerel ayarlar (API anahtarları — dışarı gitmez)"),
        ("harita\\veri\\", "arşiv.db · merkez.json · uyarilar.json · kumanda.json · önbellek"),
        ("harita\\BAŞLAT.bat / GİRİŞ.bat / HARİTA.bat / DURDUR.bat", "çift tıkla çalıştırma"),
        ("referans\\", "28 ekran görüntüsü + canlı hareket GIF'i (kanıt)"),
        ("OKU-BENI.md / KAYNAKLAR.md", "kullanım ve kaynak belgeleri"),
    ]:
        madde(doc, s + " — " + ac)
    doc.add_paragraph()

    # ---------------- 10. ZAMANLANMIŞ ----------------
    surum(doc, "10. ZAMANLANMIŞ İŞLER (Hermes)", AMBER)
    tablo(doc, ["İş", "Zaman", "Ne yapar"], [
        ["Ustad Gozcu uyari koprusu", "10 dakikada bir",
         "Uyarı kuyruğunu okur, yeni olay varsa WhatsApp'a Türkçe mesaj atar "
         "(olay yoksa sessiz kalır)"],
        ["Ustad Gozcu gunluk rapor", "Her akşam 21:00",
         "Renkli Word raporunu üretir, Masaüstü'ne bırakır, WhatsApp'a haber verir"],
    ])
    doc.add_paragraph()

    # ---------------- 11. KAYNAKLAR ----------------
    surum(doc, "11. VERİ KAYNAKLARI (tamamı açık / anahtarsız)", MOR)
    for k in ["OpenSky + adsb.lol + adsb.fi — uçaklar (irtifa, hız, yön, dikey hız)",
              "Finlandiya AIS (meri.digitraffic.fi) — gemiler (MMSI, rota, hız)",
              "CelesTrak TLE + SGP4 — uydular", "USGS — depremler",
              "NASA EONET — yangınlar ve doğa olayları", "GDACS — afet uyarıları",
              "OurAirports — havalimanları", "WRI Global Power Plant — santraller",
              "TeleGeography/OSM — denizaltı kabloları", "TfL JamCams — kameralar",
              "Open-Meteo (hava · hava kalitesi · deniz) — 81 il + kıyılar",
              "RainViewer — yağış radarı", "NASA GIBS — günlük uydu fotoğrafı",
              "Wikidata — limanlar, volkanlar, şirket merkezleri",
              "OpenStreetMap (Overpass) — büyükelçilikler, demiryolları",
              "PB2002 — levha sınırları", "GEM — diri fay hatları",
              "NOAA — tsunami uyarıları", "Manifold + Yahoo + CoinGecko + Frankfurter — piyasalar",
              "cihadturhan/tr-geojson — 81 il sınırı", "CARTO / Esri — harita zeminleri"]:
        madde(doc, k)
    doc.add_paragraph()

    # ---------------- 12. AKTİF / BEKLEYEN ----------------
    surum(doc, "12. NELER AKTİF · NELER BEKLİYOR", RED)
    madde(doc, "AKTİF (çalışıyor):", True, TEAL)
    for k in ["26 araç düğmesi, 7 ek modül, 64 hedefli sesli komut",
              "Canlı uçak + gemi hareketi (ölü hesap)", "Yağış radarı + tarihli uydu fotoğrafı",
              "Harekât odası + canlı olay akışı", "Arşiv + zaman makinesi",
              "Uyarı zinciri (WhatsApp + halka + anons)", "Telefondan kumanda (39 düğme)",
              "Günlük Word raporu (21:00 otomatik)", "MCP (6 araç)", "2. ekran (video/TV)"]:
        madde(doc, k)
    madde(doc, "BEKLEYEN (anahtar gerekiyor):", True, AMBER)
    madde(doc, "AISStream anahtarı → dünya geneli gemiler (şu an kaynak Baltık; "
               "Türkiye görünümünde gemi yok)")
    madde(doc, "NASA FIRMS MAP_KEY → uydu yangın tespiti (şu an yangınlar EONET'ten)")
    madde(doc, "Demiryolu katmanı: Overpass sunucusu yoğun olduğunda boş döner "
               "(kendiliğinden dolar, önbelleğe yazılmaz)")
    madde(doc, "Yerel yapay zekâ özeti: Ollama bu makinede kurulu değil "
               "(kurulunca düğme çalışır; uydurma özet üretmez)")
    doc.add_paragraph()

    # ---------------- 13. KURALLAR ----------------
    surum(doc, "13. ÇALIŞMA KURALLARI (dürüstlük)", GRI)
    for k in ["Sahte veri yok: kaynak düşerse sayaç 'veri yok' / 'son bilinen' der, 0 yazmaz.",
              "Hız/yön bilinmiyorsa uçak/gemi yerinde durur — uydurma hareket yapılmaz.",
              "Argos Atlas'ın markası/logosu kopyalanmadı; kendi madalyonu ve adı kullanılıyor.",
              "Onların sunucusu kaynak olarak kullanılmaz; aynı birincil açık kaynaklardan çekilir.",
              "API anahtarları yalnız yerel ayar.json'da tutulur, hiçbir yere gönderilmez."]:
        madde(doc, k)

    doc.add_paragraph()
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    k = p.add_run("ÜSTAD GÖZCÜ · açık veriyle çalışan yerel izleme paneli · ÜSTAD KENAN KUZUCU")
    k.font.size = Pt(9)
    k.font.color.rgb = RGBColor.from_string(GRI)

    ad = "USTAD-GOZCU-TUM-LISTE-" + simdi.strftime("%Y-%m-%d") + ".docx"
    tam = os.path.join(MASAUSTU, ad)
    try:
        doc.save(tam)
    except PermissionError:
        # dosya Word'de açık: yeni adla kaydet (Kenan'ı bekletmeyelim)
        ad = "USTAD-GOZCU-TUM-LISTE-" + simdi.strftime("%Y-%m-%d_%H%M") + ".docx"
        tam = os.path.join(MASAUSTU, ad)
        doc.save(tam)
    try:
        kopya_klasor = os.path.join(PROJE, "raporlar")
        os.makedirs(kopya_klasor, exist_ok=True)
        doc.save(os.path.join(kopya_klasor, ad))
    except Exception:
        pass
    return tam


def son_surum():
    try:
        return str(al("/saglik", 10).get("surum", "?"))
    except Exception:
        return "?"


# ---- envanter (Playwright çıktısı varsa ondan, yoksa sabit liste) ----
def envanter_oku():
    global DUGMELER, UCLAR, SES_HEDEF
    yol = os.path.join(os.environ.get("TEMP", "C:/tmp"), "envanter.json")
    for aday in (r"C:\tmp\envanter.json", yol, "/tmp/envanter.json"):
        if os.path.isfile(aday):
            try:
                d = json.load(open(aday, encoding="utf-8"))
                DUGMELER = d.get("dugmeler") or []
                if d.get("sesHedef"):
                    SES_HEDEF = int(d["sesHedef"])
                break
            except Exception:
                pass
    if not DUGMELER:
        DUGMELER = [{"ad": "(envanter dosyası okunamadı — panel açıkken tekrar üretin)"}]
    try:
        UCLAR = al("/api", 15).get("uclar", [])
    except Exception:
        UCLAR = []


DUGMELER = []
UCLAR = []
SES_HEDEF = 73

if __name__ == "__main__":
    try:
        envanter_oku()
        print("Word listesi hazır:", uret())
    except Exception as hata:
        import traceback
        print("LİSTE ÜRETİLEMEDİ: %s: %s" % (type(hata).__name__, hata))
        traceback.print_exc()
        sys.exit(1)
