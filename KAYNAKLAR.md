# Doğrulanmış Veri Kaynakları

Bu listedeki uçlar tek tek test edildi ve panelde canlı olarak çalışıyor.
Durum: YAYINDA = panelde açık ve veri akıyor.

## Panelde canlı (dokuz katman)

| Katman      | Uç                                                | Anahtar | Durum |
|-------------|---------------------------------------------------|---------|-------|
| Uçaklar (dünya + orta) | https://opensky-network.org/api/states/all (+bbox) | yok | YAYINDA (~8.900 uçak, tek istek) |
| Uçaklar (yakın) | https://api.adsb.lol/v2/point/{lat}/{lon}/250      | yok     | YAYINDA |
| Uçaklar (yedek) | https://opendata.adsb.fi/api/v2/lat/{lat}/lon/{lon}/dist/250 | yok | YAYINDA |
| Gemiler     | https://meri.digitraffic.fi/api/ais/v1/locations           | yok     | YAYINDA (gzip başlığı ŞART) |
| Depremler   | https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/2.5_day.geojson | yok | YAYINDA |
| Yangınlar   | https://eonet.gsfc.nasa.gov/api/v3/events?status=open      | yok     | YAYINDA |
| Doğa olayları | aynı EONET ucu, wildfires dışındaki kategoriler          | yok     | YAYINDA |
| Havalimanları | https://davidmegginson.github.io/ourairports-data/airports.csv | yok | YAYINDA |
| Uydular     | https://db.satnogs.org/api/tle/?format=json                | yok     | YAYINDA (SGP4 ile) |
| Kablolar    | https://www.submarinecablemap.com/api/v3/cable/cable-geo.json | yok  | YAYINDA |
| Kameralar   | https://api.tfl.gov.uk/Place/Type/JamCam                   | yok     | YAYINDA (Londra, 890) |
| Harita zemini | https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json | yok | YAYINDA |

## Bekleyen / erişilemeyen kaynaklar

| Kaynak                              | Durum | Not |
|-------------------------------------|-------|-----|
| AISStream.io (dünya geneli gemi)     | anahtar gerekli | ücretsiz, e-posta ile kayıt; anahtar gelince WebSocket toplayıcı yazılacak |
| NASA FIRMS (yangın noktaları)        | anahtar gerekli | EONET zaten yangın veriyor, FIRMS şart değil |
| CelesTrak TLE                        | erişilemedi | bu ağdan yanıt yok; SatNOGS kullanılıyor |
| GDELT                                | 429 | sürekli çok istek yanıtı; EONET ile değiştirildi |
| UCDP                                 | 401 | artık token istiyor |
| OpenSanctions                        | 401 | anahtar istiyor |
| Overpass (OSM)                       | 504 | yoğun; santral katmanı için tekrar denenecek |
| KGM kameraları                       | yok | sayfalar 404; açık kamera API'si bulunamadı |
| İBB açık veri kamera                 | yok | CKAN aramasında kamera veri seti yok |
| Caltrans (Kaliforniya kameraları)    | zaman aşımı | bu ağdan erişilemedi |

## Doğrulanmış doğruluk notu

SGP4 hesabımız ISS için wheretheiss.at ile karşılaştırıldı:
enlem 0.42°, boylam 0.30° fark (TLE yaşı ~3,5 saat). Harita ölçeğinde
bu fark görünmez; konum doğru kabul edilir.

## Yasal çerçeve

- Bir başkasının API'sini çekmek YOK: kendi kaynağımızdan besleniyoruz.
- OSM verisi ODbL: atıf şart. CARTO/Esri/OurAirports/EONET/SatNOGS/
  submarinecablemap/TfL: atıf ile serbest, anahtar istemiyor.
- Kamera görüntüleri resmî trafik kameralarıdır; yüz/plaka tanıma
  yapılmıyor, arşiv tutulmuyor, yalnız son kare gösteriliyor.

