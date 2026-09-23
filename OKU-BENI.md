# ÜSTAD GÖZCÜ

Dünyayı canlı izleyen tek harita paneli.
Uçaklar · Gemiler · Kameralar · Uydular · Yangınlar · Depremler · Olaylar · Altyapı

> Şiar: "Gözcü hiç kırpmaz." (We never blink)

---

## Klasör düzeni

```
USTAD-GOZCU/
  OKU-BENI.md        bu dosya — proje planı
  KAYNAKLAR.md       doğrulanmış veri kaynakları listesi
  harita/
    index.html       HARİTA (MapLibre GL, dokuz katman) — ana uygulama
    giris.html       GİRİŞ EKRANI (küre, şerit, başlık)
    sunucu.py        veri köprüsü, port 8811
    kutuphane/       gömülü sgp4 (uydu yörünge hesabı)
    foto/            madalyon
    BASLAT.bat / DURDUR.bat
  veri/              veri toplama boru hattı
    onbellek/        indirilen dosyalar (OurAirports, kablolar)
  referans/          panelin ekran görüntüleri
```

## Neden ayrı klasör

Mevcut `USTAD-DUNYA-MONITOR` (radyo/IPTV/kasa paneli) ve
`USTAD-SIBER-EGITIM` ile karışmasın. Bu üçüncü, bağımsız bir ürün.

---

## Katman durumu

| # | Katman           | Kaynak (birincil)                     | Durum |
|---|------------------|---------------------------------------|-------|
| 1 | Harita zemini    | CARTO Dark Matter (açık stil)         | YAYINDA |
| 2 | Uçaklar          | OpenSky (geniş) + adsb.lol/adsb.fi (yakın) | YAYINDA (dünya ~8.900) |
| 3 | Gemiler          | meri.digitraffic.fi açık AIS          | YAYINDA (Baltık) |
| 4 | Depremler        | USGS GeoJSON (anahtarsız)             | YAYINDA |
| 5 | Yangınlar        | NASA EONET (anahtarsız)               | YAYINDA |
| 6 | Doğa olayları    | NASA EONET (anahtarsız)               | YAYINDA |
| 7 | Havalimanları    | OurAirports (kamu malı)               | YAYINDA |
| 8 | Uydular          | SatNOGS TLE + SGP4 (anahtarsız)       | YAYINDA |
| 9 | Denizaltı kabloları | submarinecablemap.com (açık)       | YAYINDA |
|10 | Kameralar        | Transport for London JamCams          | YAYINDA (Londra) |
|11 | Santraller       | WRI Global Power Plant (kamu malı)    | YAYINDA (34.936) |
|12 | Afet uyarıları   | GDACS (anahtarsız)                    | YAYINDA (69) |
|13 | Boğazlar         | sabit darboğaz listesi               | YAYINDA (19) |
|14 | Tahmin piyasaları| Manifold Markets (anahtarsız)         | YAYINDA (180) |
|15 | Piyasalar        | Finnhub (anahtarlı) + Yahoo           | YAYINDA (79 enstrüman) |
|16 | Dünya geneli gemi| AISStream.io                          | ANAHTAR GEREKİYOR (Kenan) |
|17 | Türkiye kameraları | KGM / belediyeler                   | AÇIK SERVİS YOK |

On dört katman canlı yayında. Kalanlar "SIRADAKİ İŞLER" bölümünde.

---

## HARİTA DÜZENİ — argosatlas düzeni (v0.4.0)

Argos haritasının arayüzü birebir örnek alındı:

  Sağ üst     YEDİ KATEGORİ ÇİPİ (canlı sayıyla):
              Kameralar · Uçaklar & gemiler · Uydular · Altyapı ·
              Olaylar · Tahminler · VIP & kuruluşlar
              Çipe tıkla → altında FİLTRE ÇEKMECESİ açılır.
  Çekmece     Her katman bir bölüm: adı + sayısı + aç/kapa anahtarı.
              Alt türler iki sütunlu balıkçı (pill) düğmeleriyle:
              santral türü (Nükleer, Kömür, ... Atık), olay türü.
              Seçim yoksa hepsi gösterilir.
  Sol alt     Üç araç: uydu görüntüsü (Esri), gece/gündüz sınırı
              (gerçek güneş hesabı), bu alanı izle (kutu + sayaçlar).
  Sağ alt     Yakınlaştır / uzaklaştır / beni bul (eskiden beri var).
  Alt şerit   Hakkında · Kaynaklar ve yöntem · Yasal uyarı · Gizlilik ·
              Atıflar — beşi de gerçek bilgi penceresi açar.

YENİ KATMANLAR (hepsi anahtarsız, doğrulandı):
  santral  10.701 santral  — WRI Global Power Plant Database (kamu malı)
  gdacs        69 olay     — GDACS (fırtına, sel, volkan, yangın, kuraklık)
  bogaz        19 boğaz    — sabit darboğaz listesi (Hürmüz, Malakka, ...)
  tahmin      180 piyasa   — Manifold Markets açık API

**ANAHTAR GEREKTİREN BÖLÜMLER (en sonda, sonraki adım):**
  VIP & kuruluşlar çipi şimdilik sadece bilgi gösterir. İçindekiler:
  şirket merkezleri, VIP kişiler, borsa / ETF / tahvil / emtia / endeks /
  döviz kotasyonları, hükümet ve kuruluş merkezleri. Hepsi anahtarlı ya
  da ücretli servislerde (Polygon, Finnhub, FMP, Kalshi, Mapbox...).
  Sabah anahtarlarla birlikte açılacak.

---

## v0.5.0 — PRO özelliklerinin bedava karşılıkları (dört araç)

Argos PRO'nun sattığı "hatırlar / uyarır / dışa aktarır / kontrol odası"
işleri kendi sunucumuzda kuruldu. Hepsi yerel, hepsi anahtarsız.

  ARŞİV (geçmişe sarma)      sol alt 🕐 düğmesi
    Sunucu her 2 dakikada bir katmanları SQLite'a yazar
    (veri/arsiv.db, 72 saat, katman başına 9.000 nokta, gzip).
    Alt şeritte: katman seç · kaydırıcı · ◀ ▶ · Oynat (animasyon) ·
    CANLI. Geçmişteyken üstte sarı "GEÇMİŞ · tarih · katman" rozeti.
    Uçlar: /veri/arsiv/saatler?kat=… ve /veri/arsiv?kat=…&t=unix
    NOT: uçak arşivi dünya anlık görüntüsünden gelir (15 dk'da bir
    tazelenir); gemi/deprem/yangın/olay/uydular 2 dakikada bir.

  UYARI + GEOFENCE           sol alt ⚠ düğmesi
    Haritayı bir yere getir → "uyarı ekle" → görünen kutu izlenir.
    İçine giren deprem/yangın/olay/uçak/gemi için masaüstü bildirimi
    ve panel kaydı düşer (localStorage'da saklanır, 📋 ile liste).
    İlk tarama taban çizgisidir: mevcutlar "yeni" sayılmaz.

  DIŞA AKTARMA               filtre çekmecesinde her bölümün altında
    CSV (noktalı virgül, BOM — Excel-TR uyumlu) · KML (Google Earth,
    çizgi/çoklu çizgi/poligon desteği) · GeoJSON.

  VİDEO DUVARI + TV MODU     sol alt ▦ ve ▭ düğmeleri
    Video duvarı: görünen alana en yakın 16 kamera, kareye tıkla →
    canlı video (TfL .mp4). TV modu: tam ekran kontrol odası —
    büyük saat, kategori sayaçları, arayüz gizli (ESC ile çıkılır).

---



## v0.7.0 — HAREKÂT ODASI (askerî şura görünümü)

Sol altta kalkan düğmesi (ek-hko) → tam ekran "harekât odası":
  - Köşe kelepçeleri (dört köşe, simetrik) + aşağı kayan tarama çizgileri
  - Ortada HAREKÂT ODASI başlığı, saat ve o anki bölge adı
  - Solda 5, sağda 5 canlı sayaç (odada tembel katmanlar kendiliğinden yüklenir)
  - Sağ altta RADAR: gerçek noktalardan blipller (uçak yeşil, gemi mavi,
    deprem turuncu, yangın kırmızı), dönen tarama çizgisi, "N TEMAS"
  - Sol altta tehdit seviyesi çubuğu (nabız animasyonu), izlenen alan sayısı,
    arşiv bilgisi, konum/zoom
  - Altta akan durum bandı (bütün sayaçlar + kaynak listesi)
  - GEZİNTİ: gözcü kendi gezer — 16 bölge arasında 12 sn'de bir yumuşak
    uçuş (Türkiye → Ege → Doğu Akdeniz → Kafkasya → ... → Kuzey Kutbu → baştan)
  - Oda açıkken çipler/çekmece/arşiv şeridi/katman paneli/ray gizlenir
  - Çıkış: "ODADAN ÇIK ✕" düğmesi, kalkan düğmesi ya da ESC

---



## Giriş ekranı (giris.html)

  Harita AYRI dosyadır: index.html. Giriş ekranı haritayı açmaz yerine
  kendi dosyasında durur; "HARİTAYI AÇ →" düğmesi index.html'e gider.

  Üst bar      Madalyon + "ÜSTAD GÖZCÜ" · Katmanlar · Kaynaklar ve yöntem ·
               Hakkında · Kullanım · sağda canlı saat, "SİSTEM ÇEVRİMİÇİ",
               TR, "Nasıl kullanılır", "HARİTAYI AÇ →"
  Kayan şerit  Sekiz canlı sayaç soldan sağa akar; üstüne gelince durur
  Sol          Etiket, büyük başlık, renkli anahtar kelimeli paragraf,
               "Haritayı aç →" düğmesi, "Ücretsiz · hesap gerekmez"
  Sağ          DÖNEN DÜNYA KÜRESİ — köşe ayraçları içinde
                 Sürükle → elle döndürür (4 sn sonra kendi dönüşüne döner)
                 Üstüne gel → alttaki ENLEM/BOYLAM o noktayı gösterir (beyaz)
                 Tıkla → o noktayı haritada açar (index.html?la=..&lo=..&z=6)
               Noktalar gerçek veri: kıtaların şekli havalimanlarından,
               parlak noktalar canlı uçak, uydu, yangın ve depremlerden.
  Alt          Kaynak ve yasal not şeridi

  Küre süs değil, çalışan bir giriş kapısıdır. Referans sitede (argosatlas)
  küre tıklamaya tepki vermiyor; buradaki etkileşim bilinçli bir farktır.

---

## NASIL ÇALIŞTIRILIR

    harita\BASLAT.bat     ← sunucuyu açar + giriş ekranını açar
    harita\GIRIS.bat      ← yalnız GİRİŞ EKRANI (giris.html)
    harita\HARITA.bat     ← yalnız HARİTA       (index.html)
    harita\DURDUR.bat     ← sunucuyu kapatır

Üç kısayol da akıllı: sunucu zaten çalışıyorsa beklemeden ilgili sayfayı
açar; çalışmıyorsa sunucuyu başlatıp sayfayı açar. O pencere kapanırsa
panel de kapanır.

GİRİŞ EKRANI:  http://127.0.0.1:8811/giris.html
    Kayan canlı sayaç şeridi, dönen dünya küresi (noktaları gerçek
    uçak/uydu/yangın/havalimanı verisinden), büyük başlık.
    "HARİTAYI AÇ →" düğmesi veya Enter tuşu haritaya geçirir.

HARİTA:  http://127.0.0.1:8811/index.html   (kök adres de bunu açar)
    Konum ve katman bağlantısı:
      index.html?la=41.05&lo=28.95&z=8
      index.html?la=51.5&lo=-0.13&z=10.5&kat=kamera
    (?kat=... yazılan katmanlar açılır, diğerleri kapanır)
    Haritada sol üstteki "ÜSTAD GÖZCÜ" yazısına tıklayınca giriş
    ekranına döner.

Neden sunucu gerekiyor: veri kaynakları tarayıcıya CORS izni vermiyor.
`sunucu.py` istekleri kendi üzerinden geçirir, ayrıca kare kare önbellek
tutar (haritayı kaydırmak yeni yük getirmez).

Konum bağlantısı:  http://127.0.0.1:8811/?la=41.05&lo=28.95&z=8

Kısayollar:  T = tema · K = katman paneli · Boşluk = Türkiye'ye dön

## ŞU AN ÇALIŞAN (dokuz katman)

  - UÇAKLAR         canlı, 12 sn'de tazelenir, irtifaya göre renkli ikon,
                    tıkla → çağrı adı, tescil, tip, irtifa, hız, yön
  - GEMİLER         canlı AIS, rota yönünde dönmüş gemi ikonları (Baltık)
  - UYDULAR         1.580+ uydu, SGP4 yörünge hesabı, tıkla → NORAD/irtifa
  - DEPREMLER       USGS son 24 saat, büyüklüğe göre boyut ve renk
  - YANGINLAR       NASA EONET, dünya geneli orman yangınları
  - DOĞA OLAYLARI   EONET fırtına ve diğer açık olaylar
  - HAVALİMANLARI   72.570 kayıt; haritada 5.280 büyük+orta meydan
  - KABLOLAR        730 denizaltı kablosu, renkli hatlar
  - KAMERALAR       890 resmî Londra kamerası; tıkla → CANLI görüntü
  - Yer arama, yuvarlak dünya, saat, koordinat, 6 tema, sağ ikon rayı

Konum/katman bağlantısı:
    http://127.0.0.1:8811/?la=41.05&lo=28.95&z=8
    http://127.0.0.1:8811/?la=51.5&lo=-0.13&z=10.5&kat=kamera
    (?kat=... yazılan katmanlar açılır, diğerleri kapanır)

## SIRADAKİ İŞLER

  1. DÜNYA GENELİ GEMİ — AISStream.io ücretsiz anahtar istiyor (e-posta).
     Anahtar gelince sunucuya WebSocket toplayıcısı yazılacak; AISStream
     mesajları zaten çözülmüş JSON gönderiyor, NMEA çözmek gerekmiyor.
  2. TÜRKİYE KAMERALARI — KGM ve belediyeler kamera görüntüsünü açık API
     olarak YAYINLAMIYOR. İBB açık veri portalında da kamera veri seti yok
     (kamera/trafik/görüntü aramaları denendi). Yapılabilir yol: şehir
     sitelerini tek tek inceleyip kazımak. Kenan hangi şehri/kanalı
     izlemek istediğini söylerse oradan başlanır.
  3. SANTRALLER — WRI açık santral veritabanı + OSM'den enerji altyapısı.
  4. UYDU GÖRÜNTÜSÜ — harita altlığını Esri uydu moduna çeviren anahtar.

## KISAYOLLAR

  T        tema değiştir (6 tema)
  K        katman paneli aç/kapa
  Boşluk   Türkiye'ye dön

## BİLİNEN SINIRLAR

  - UÇAKLAR: üç kademeli yol var.
      1. Dünya görünümü ve giriş ekranı → OpenSky tek istekte bütün dünyayı
         verir (~8.900 uçak). 15 dakika önbelleklenir (anonim günlük kota).
      2. Orta yakınlık → yine OpenSky, tek istekte görünen kutu.
      3. Sokak seviyesi → adsb.lol / adsb.fi 250 deniz mili kareler.
    Yani dünya görünümü artık seyrek değil; yoğunluk gerçek trafiği yansıtır.
  - Gönüllü ADS-B ağları (adsb.lol, adsb.fi) saniyede birden fazla isteği
    kabul etmiyor. Sunucu kaynak başına 1,2 saniye aralık koyar, 429 yerse
    katlanarak artan süreyle geri çekilir (90 → 180 → 360 → 720 → 900 sn)
    ve o sırada son bilinen konumları gösterir. Boş harita göstermez.
  - Türkiye üzerindeki kapsama, gönüllü alıcı sayısına bağlı; kalabalık
    Avrupa'ya göre daha seyrek.
  - Gemi katmanı Baltık/Kuzey Avrupa; kamera katmanı Londra; dünya geneli
    için anahtar gerekiyor (bkz. SIRADAKİ İŞLER).


## Marka notu

`ARGOS ATLAS` adı, hexagon logosu ve "We never blink" sloganı başkasının.
Bizim panelimiz kendi adımızı ve kendi logomuzu (ÜSTAD madalyonu) taşır.
Görünüm, düzen, renk paleti ve his birebir aynı olabilir — o serbest.

## Arayüz hedefi (referanstan ölçülen)

- Zemin tonu: #060c11 / #0a1014
- Ana vurgu: turkuaz #2bf0c8 · ikincil: amber #ffd23b · alarm: #ff3b4d · bilgi: #3d8bff
- Fontlar: Michroma (başlık) · Inter (arayüz) · IBM Plex Mono (sayı/saat)
- Üst sağ: renk kodlu canlı sayaç tablosu
- Sağ kenar: 12'li dikey ikon rayı, aktif olan parlar
- Sol alt: yuvarlak dünya mini-harita + UTC saat + koordinat
- Alt şerit: bağlantılar

---

# v0.8.0 / v0.9.0 — UYARI KÖPRÜSÜ, İZ, DALGA, RAPOR, KML, İL SINIRLARI, MCP

Bu sürümde panelin "hatırla / uyar / anlat" tarafı kuruldu. Ana harita koduna
dokunulmadı: her şey `index.html` sonundaki AYRI `<script>` bloğunda ve
`sunucu.py` içindeki ayrı bölümlerde yaşar.

## Sunucu (sunucu.py → SURUM 0.8.0)

| Bölüm | Ne yapar |
|---|---|
| **Uyarı motoru** | `veri/uyarilar.json` içindeki bölgeleri 2 dakikada bir tarar (panel kapalıyken de). Bölgeye giren yeni uçak/gemi/deprem/yangın/olay/afet uyarısını `veri/bildirim-kuyrugu.jsonl` dosyasına yazar. |
| Gürültü kesme | `UYARI_SESSIZ`: uçak/gemi için bölge başına **1 saat** sessizlik; deprem/yangın/afet sınırsız. |
| **İl sınırları** | `/veri/il` → 81 il (açık GeoJSON, 30 gün önbellek). |
| **Günlük rapor** | `/veri/rapor` → katman sayıları + en büyük depremler + uyarılar (5 dk önbellek). |
| **API listesi** | `/api` → 26 ucun Türkçe açıklaması. |
| **Uçak/gemi izi** | `/veri/arsiv/iz?kat=ucak&ad=<kod>&saat=72` → arşivdeki konum zinciri. |
| Panel yazma ucu | `POST /veri/uyari` (bölge ekle), `POST /veri/uyari/sil` (indis ile sil). |

## Panel (16 araç düğmesi)

| Düğme | İş |
|---|---|
| 🌊 dalga | Son 24 saatin en büyük **12 depremine** yayılan halka (büyüklüğe göre kalınlık/çap). |
| 〰 iz | Haritada bir **uçağa/gemiye tıkla** → son 72 saatlik izi sarı kesikli çizgi olarak çizilir, harita ize sığar. |
| 🔊 ses | Türkçe **sesli anons**: yeni M≥4,5 deprem ve uyarı bölgesi kaydı okunur (`localStorage: ustad-gozcu-ses`). |
| 🌙 koruyucu | **5 dakika hareketsizlik → harekât odası** kendiliğinden açılır (video duvarı/TV/oda zaten açıksa açmaz). |
| 📄 rapor | Günlük rapor penceresi + **.txt indir** (BOM'lu, Excel/Not Defteri uyumlu). |
| ⤓ KML | **Google Earth'te çizdiğin alanı** içe aktarır: Polygon → uyarı bölgesi (sunucuya yazılır), LineString → haritada pembe çizgi. |
| 🗺 il | Türkiye **il sınırları** (81 il, turkuaz dolgu + çizgi, veri katmanlarının altında). |
| ▭ TV | TV modunda harita **55° eğilir ve yavaşça döner** (3D); çıkışta 0°'ye döner. |

## Köprü (harita/bildirim.py + Hermes zamanlayıcısı)

1. `python bildirim.py` → gönderilmemiş uyarıları Türkçe özetler, kuyruğu işaretler;
   yeni uyarı yoksa **hiç çıktı vermez** (gürültü yapmaz).
2. `python bildirim.py --test` → deneme mesajı.
3. `--hepsi` → son 20 kayıt.
4. Webhook: `ayar.json` içine `discord_webhook` ya da
   `telegram_bot_token` + `telegram_chat_id` konursa doğrudan gönderir;
   yoksa çıktıyı Hermes cron teslim eder.
5. Kurulu Hermes işi: **"Ustad Gozcu uyari koprusu"** (`gozcu-uyari.py`, her 10 dakika,
   `no_agent`, teslim: WhatsApp).

## MCP (harita/mcp_gozcu.py)

Hermes `config.yaml` içine eklendi (`mcp_servers.ustad-gozcu`); sınamada **6 araç**
göründü. Sohbetten şunlar sorulabilir: katman sayıları, bir katmanın kayıtları
(kutu süzgeçli), günlük rapor, uyarı bölgeleri, bölge ekle/sil.

```yaml
mcp_servers:
  ustad-gozcu:
    command: python
    args:
      - C:/Users/kenan/OneDrive/Desktop/USTAD-GOZCU/harita/mcp_gozcu.py
```

## Varsayılan uyarı bölgeleri

- **Gaziantep ve çevresi** — deprem, yangın, doğa olayı, afet uyarısı
- **Türkiye geneli** — deprem, afet uyarısı

(2 dakikada bir taranır; uçak/gemi katmanları bilerek seçilmedi — şehir üstünde
uçak sürekli görünür, bildirim yağmuru olurdu.)

---

# v0.10.0 — CANLI UÇAK HAREKETİ (pürüzsüz animasyon)

Uçaklar artık 30 saniyelik raporda **zıplamıyor**: her rapordaki **hız (g, knot)**
ve **yön (d, derece)** ile konum 200 ms'de bir ilerletiliyor (ölü hesap).
Kenan'ın isteği: *"uçakların hareketli animasyon hâli"*.

## Nasıl çalışır

- `index.html` sonundaki DÖRDÜNCÜ ek blok. Kaynak `ucakcanli`, katman
  `ucak-canli-ikon` (statik `ucak-ikon` ile aynı simge stili).
- Animasyon açıkken statik katman gizlenir; tıklama bilgi kutusu canlı katmana
  da bağlandı (aksi hâlde uçağa tıklamak işe yaramazdı).
- **Görünen alan (+%30 pay) dışındaki uçaklar çizilmez** — 9.000 uçağı her
  karede yeniden göndermek haritayı kilitlerdi. Hesap hepsi için yapılır,
  gönderilen en fazla 2.500 nokta (daha fazlası seyreltilir).
- Hız/yön bilinmiyorsa ya da uçak yerdeyse (y=1) **yerinde durur** — uydurma
  hareket yok.
- Düğme: `#ek-hareket` (17. düğme). Ayar `localStorage: ustad-gozcu-hareket`
  (varsayılan AÇIK). `window.gozcuHareket = {baslat, durdur, durum, sayi}`.

## Doğrulama (sayıyla)

| Ölçüm | Sonuç |
|---|---|
| Hız doğruluğu | 390,3 kt uçak: beklenen 829,3 m / ölçülen 831,5 m → **oran 1,003** |
| Yön | Rapor 315° · ölçülen bileşenler kuzey +616 m / doğu −612 m (KB) ✓ |
| Pürüzsüzlük | 10 adımda 81→868 m, eşit artışlarla (zıplama yok) |
| Kapsam | Görünen 844 uçağın **809'u hareket etti**, 35'i yerde/hızı yok |
| Hata | 0 |

## Birim uyarısı (kritik)

`g` alanı **KNOT** cinsindendir (OpenSky m/s → ×1,94384; adsb.lol zaten knot).
m/s'ye çevirirken **×0,514444** kullan. `÷3,6` yazarsan uçaklar gerçek hızının
yarısında kayar ve gözle "yavaş" görünür. Paneldeki etiket de "kt" olmalı.

Kanıt: `referans/panel-19-canli-hareket.gif` (Frankfurt üstü, 20 kare).

---

# v0.11.0 — GEMİ HAREKETİ + AÇILIŞ PERDESİ

## Gemi canlı hareketi

- Uçaklarla aynı ölü hesap; ama gemi kaydında **rota alanı `y`** (COG),
  hız alanı `g` (knot). `h` pruvadır ve **511 = bilinmiyor** (AIS kuralı).
- Hızı ≤ 0,8 knot olan gemiler **oynatılmaz** (limanda demirli).
- Düğme: `#ek-gemi-hareket` (18. düğme). Ayar `localStorage: ustad-gozcu-gemi-hareket`.
- **Gemi kaynağı şu an Baltık** (Finlandiya AIS). Türkiye görünümünde gemi yoktur;
  düğme açıldığında ekranda gemi yoksa panel bunu açıkça söyler.
- Doğrulama (Baltık, zoom 6,4): 12,7 knot gemi → beklenen 39 m / ölçülen 37,6 m
  (**oran 0,964**); yön: rapor 256° · ölçülen kuzey −9 m / doğu −36 m ✓;
  1.048 gemi canlı çizildi; hata 0.

## Açılış perdesi (giriş animasyonu)

Kenan'ın isteği: *"siteyi ilk açtığımda perdeye yakışır bir giriş animasyonu,
çok güzel bir söz"*.

- Sıra: madalyon (büyüyerek + turkuaz halka) → **ÜSTAD GÖZCÜ** harf aralığı
  açılışı → altın çizgi → **günün sözü** (kelime kelime) → imza →
  perde iki yana ayrılır → harita.
- Süre ~6,1 saniye; **ATLA** düğmesi, perdeye tıklama, ESC/boşluk/Enter ile atlanır.
- Sol altta sistem açılış günlüğü (uyduda bağlantı kuruldu → 16 katman hazır),
  sağ altta koordinat ve gözcü adı.
- **Günün sözü** 6 söz arasından güne göre seçilir (`SOZLER` dizisi).
  Üçü Kenan'ın kendi sözü, üçü doğrulanabilir klasikler (Atatürk, Yunus Emre,
  Mevlânâ). Yeni söz eklemek için dizinin sonuna ekle — başka dosyaya dokunma.
- Kapatma: `?perde=0` adres parametresi ya da `localStorage.ustad-gozcu-perde='0'`.
- `window.gozcuPerde.goster()` ile istendiği an yeniden oynatılır.
- Kanıt: `referans/panel-20-acilis-perdesi.png`, `panel-21-perde-acilisi.png`.

---

# v0.12.0 — YENİ KATMANLAR + HARİTA ARAÇLARI

Sol altta **KATMANLAR** düğmesi → panel açılır; her katman bağımsız aç/kapa.

## A) 8 yeni katman (hepsi açık/anahtarsız veri)

| Katman | Kaynak | Uç | Kayıt |
|---|---|---|---|
| Hava Durumu | Open-Meteo | /veri/hava | 81 il (sıcaklık, rüzgâr, yağış, durum) |
| Hava Kirliliği | Open-Meteo hava kalitesi | /veri/kirlilik | 81 il (PM2.5 + AQI + seviye) |
| Deniz Durumu | Open-Meteo deniz | /veri/deniz | 16 kıyı noktası (dalga, periyot, su sıcaklığı) |
| Limanlar | Wikidata | /veri/liman | **4.564** liman |
| Volkanlar | Wikidata | /veri/volkan | **2.243** volkan |
| Levha Sınırları | PB2002 | /veri/levha | **241** levha çizgisi |
| Diri Fay Hatları | GEM | /veri/fay?b=g,b,k,d | Türkiye kutusunda **407** fay |
| Demiryolları | OpenStreetMap | /veri/tren | TR kutusu (Overpass yoğunken boş dönebilir) |

Her noktaya tıklayınca sağ altta bilgi kutusu açılır (ör. Adana · 29 °C · Az bulutlu · rüzgâr 18 km/sa).

## B) Yağış radarı (RainViewer, canlı)
/veri/radar 9 geçmiş kare + 3 tahmin karesi verir; panel 0,7 sn'de bir kareyi
döndürerek **son 2 saatin yağışını** oynatır. Düğme: ☔ / panel satırı.
Karo adresi panele hiç yazılmaz, sunucudan gelir.

## C) Uydu fotoğrafı (NASA GIBS, tarih seçmeli)
/veri/uydu-foto?tarih=YYYY-AA-GG → TrueColor karo şablonu (azami zoom 9).
Paneldeki tarih kutusundan istediğin günün gerçek uydu görüntüsü katman olarak gelir.

## D) Uçak iz kuyruğu (➤ düğmesi)
Canlı hareket motorundan (v0.10.0) her 4 sn'de konum örneklenir, uçak başına son
**16 nokta (~1 dakika)** tutulur ve çizgi katmanı olarak çizilir.

## E) Uçak etiketleri (🏷)
ucaklar kaynağından çağrı kodları; **7. yakınlaştırmadan** sonra görünür
(statik kaynak kullanıldığı için performansı etkilemez).

## F) İrtifa süzgeci
Panelde kaydırıcı (0–40.000 ft). Değer 0'dan büyükse uçak katmanlarının hepsine
irtifa süzgeci uygulanır; seçim hatırlanır.

## G) Katman paneli
8 yeni katman + radar + uydu + iz + etiket + tsunami listesi + irtifa süzgeci.
Açık katmanlar tarayıcıda saklanır; panel her açılışta geri gelir.

---

# v0.13.0 — CANLI DENEYİM PAKETİ

## H) Zaman makinesi (⏱)
Arşivi (72 saat, 6 katman, 2 dk aralık) **film gibi** oynatır: katman seç,
zaman aralığı seç (1–72 saat), OYNAT. En fazla ~70 kare, 300 ms aralıkla,
soldaki çubukla elle kaydırılabilir. Kayıt sayısı her karede yazılır.

## I) Sesli komut (🎤)
Chrome/Edge'de Türkçe dinler. Örnek komutlar:
"gemileri aç", "uçakları kapat", "harekât odası", "radar", "iz kuyruğu",
"etiketler", "zaman makinesi", "rapor oku", "video duvarı", "tv modu",
"tema", "ekran koruyucu", "katman paneli", "hava durumu".
Anlaşılan komut ekranda yazılır, tanınmazsa sesli olarak söylenir.

## J) Telefondan kumanda (📱)
- Panel kumanda.html adresini tarayıcıda açar (aynı ağ şart).
- Telefondaki düğme → POST /veri/kumanda → kuyruk dosyası
  (veri/kumanda.json) → panel **2,5 sn'de bir** okuyup uygular.
- Desteklenen komutlar: katman/ yeni katman aç-kapa, radar, iz, etiket, panel,
  harekât odası, dalga, ekran koruyucu, ses, tema, rapor, tv, video, zaman,
  bölgeye git (Türkiye/Dünya/Gaziantep/İstanbul/Ege/Baltık), bildirim.
- Kuyrukta yalnız son 30 komut tutulur; 1 saatten eskiler silinir.

## K) Olay → bildirim zinciri
Uyarı motoru bir bölgeye olay yazdığında panel 20 sn'de bir /veri/uyari
okur; yeni olayda: **haritada kırmızı yayılan halka** + **Türkçe sesli anons** +
ekran bildirimi + harekât odası akışına satır.
(WhatsApp köprüsü v0.8.0'den beri ayrı çalışıyor.)

## L) Sesli günlük özet (🔊)
/veri/rapor metninden sayı satırlarını seçip Türkçe okur. Her akşam **21:00'de**
sayfa açıksa kendiliğinden bir kez okur.

## M) 2. ekran (🖥)
?sade=video veya ?sade=tv ile açılan pencerede bütün arayüz gizlenir ve
yalnız video duvarı / TV modu görünür. Düğmeden tek tıkla yeni pencere açılır.

## N) Harekât odasında canlı olay akışı
Oda açılınca sağ alta **CANLI OLAY AKIŞI** paneli gelir (son 14 olay: saat,
katman, ad, bölge).

---

# Günlük Word raporu (zamanlanmış)

- Betik: harita/gozcu-rapor.py → renkli .docx üretir
- Çıktı: Masaüstü\USTAD-GOZCU-RAPOR-<tarih>.docx (+ USTAD-GOZCU\raporlar\ kopyası)
- İçerik: canlı durum, 81 il hava durumu (en serin/sıcak 5, yağışlı il sayısı),
  son 24 saatin en büyük 10 depremi, uyarı bölgeleri, piyasalar
- Zamanlama: Hermes işi **"Ustad Gozcu gunluk rapor"** (her akşam 21:00, WhatsApp bildirimi)
- Elle: python gozcu-rapor.py

## v0.14.0 — SESLE HER ŞEY (tam komut motoru)

Mikrofon düğmesi 🎤 artık **sistemin tamamını** yönetir: **73 hedef**.

| Grup | Adet | Örnek |
|---|---|---|
| Araç düğmeleri | 26 | "video duvarını aç", "harekât odasını kapat", "telefon kumandası" |
| Harita katmanları | 15 | "depremi kapat", "kameraları aç", "santralleri kapat" |
| Yeni katmanlar + panel satırları | 10 | "hava durumunu aç", "limanları aç", "etiketleri aç" |
| Bölgeler | 18 | "baltığa git", "gemi bölgesi", "gaziantebe git" |
| Temalar | 4 | "mor tema", "buz tema" |

- **Çoklu komut:** "uçakları kapat ve gemileri aç" · "radar, etiket aç"
- **Toplu:** "hepsini aç" · "hepsini kapat" · "temizle" · "neler yapabilirsin"
- **Konuşma çekimi çözümü:** "baltığa git" → Baltık, "akdenize git" → Akdeniz,
  "harekât odası" (düzeltme işareti dahil) doğru çözülür.
- **Telefondan serbest komut:** kumanda.html üstündeki kutuya yaz ya da telefon
  klavyesinin 🎤'iyle söyle → panele gider (POST /veri/kumanda, komut "yaz").
- Her komut **Türkçe sesli onaylanır** ve ekranda yazılır.

Sınav: 26/26 düğme + 15/15 katman + 10/10 yeni katman + 18/18 bölge + 4/4 tema
sesle erişilebilir · 0 sayfa hatası.

Bulunan ve düzeltilen 5 kusur:
1. `katmanDurum`/`KATMANLAR` `window`'da görünmüyor (global sözcüksel alan) →
   durum okuma isimle + try/catch.
2. `harekât` içindeki **â** boşluğa dönüşüyordu → düzeltme işaretleri eşleniyor.
3. "Harekât odası"/"zaman makinesi" düğmeleri sınıf tabanlı durum tutmuyor →
   gerçek durum kaynağı (body.hko / #y-zk).
4. "Bu alanı izle": `gorunurKutu()` sırası (güney,batı,kuzey,doğu) yanlış
   yorumlanıyordu (polygon enlem/boylam karışık) + `bilgiKutusu._yer` boşken
   çöküyordu.
5. Radar blipleri: spanX/spanY (boylam/enlem) ters kullanılıyordu → bliplar
   yanlış yerleşiyordu; uyarı alanı etiketi N/E karışıktı.

## v0.15.0 — OTOMATİK SESLİ DİNLEME (tuşa basmadan)

Panel açılır, mikrofon izni **bir kez** verilir; sonrasında mikrofon kendiliğinden dinler.
```
durum kuşağı (sağ alt):  ● DİNLİYOR — konuş   /   ● DURDU — açmak için tıkla
kuşağa tıkla          →  dinlemeyi aç/kapa
sesle                 →  "sustur" · "dinlemeyi kapat" · "otomatik dinlemeyi aç"
"gözcü" ile başla     →  "gözcü gemileri kapat" (gözcü kelimesi atılır)
```
- Konuşma bitince tarayıcı dinlemeyi kapatır; panel **0,6 sn sonra kendiliğinden yeniden başlatır**
  → kesintisiz dinleme (tuş yok).
- **Kendi sesini duymaz:** panel konuşurken (sesli anons/özet) gelen tanıma yok sayılır.
- Şartlar: Chrome/Edge · sekme önde olmalı (arka planda Chrome sayaçları yavaşlatır) ·
  tanıma için internet gerekir (Chrome'un konuşma servisi çevrimiçi çalışır).
- Ayar kalıcıdır (`localStorage: gozcu:otomatik-ses`); kapatsan bile bir dahaki açılışta hatırlar.

Sınav (sahte mikrofon motoruyla, 9/9): otomatik başladı · onend sonrası kendini yeniden
başlattı · "gemileri kapat" uygulandı · "gözcü depremi kapat" uygulandı · panel konuşurken
komut yok sayıldı · susunca uygulandı · "sustur" durdurdu ve yeniden başlamadı ·
elle açıldı · 0 sayfa hatası.

### v0.15.1 — ses hassasiyeti + "paneli aç"

- **Tanıma 6 aday verir, panel en iyi eşleşeni seçer.** Eskiden yalnız ilk aday
  kullanılıyordu; şimdi tüm adaylar hedef tablosuna göre puanlanıp komuta en
  yakın olan uygulanıyor ("kemileri kapa" → "gemileri kapat" yakalanır).
- **Yakın söyleniş (benzerlik) ölçüsü:** yazım hatası/bozuk söyleyiş düzeltilir
  ("gemi leri kapak" → Gemiler · "depremleri kapattt" → Depremler).
- **Dolgu sözcükler atılır:** "lütfen, acaba, hani, şey, şimdi, hemen, bana, bir".
- **Canlı yazı:** konuşurken kuşakta "duyuyorum: ..."; komut uygulanınca
  "duydum: ..." gösterilir. Yeniden başlatma arası 600 → 300 ms.
- **"Paneli aç" komutu:** sesli komut listesini açar ("neler yapabilirsin",
  "komut listesi" da aynı pencere). "Katman panelini aç" ise katman panelini açar.
- Pencerenin altında mikrofon durumu yazar (dinliyor / durdurulmuş).

Sınav (sahte mikrofon motoru, 8/8): 6 aday arasından doğru seçim · bozuk söyleyiş
×2 · dolgu sözcüklü cümle · "paneli aç" listeyi açtı · "katman panelini aç" paneli
açtı, listeyi açmadı · 73 hedef · 0 sayfa hatası.
