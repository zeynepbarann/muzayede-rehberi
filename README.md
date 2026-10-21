# Müzayede Rehberi

Türkiye'deki çevrimiçi müzayede sitelerindeki devam eden eserleri tek yerde toplayan, aranabilir galeri.

**Canlı site:** https://zeynepbarann.github.io/muzayede-rehberi/

## Kaynaklar
nefsmuzayede, dedemuzayede, anatoliamuzayede, kassanat, turkartproject, uxmuzayede, ranasartgallery, galeriberlin (MuzayedeApp altyapısı), artvela, sanatsalmuzayede, artam. Yalnızca herkese açık sayfalar kullanılır; giriş yapılmaz.

## Özellikler
- Sanatçı, eser, teknik ve müzayede adına göre tam metin arama (Türkçe karakter duyarsız)
- Site, sanatçı, fiyat aralığı ve bitiş süresi filtreleri; sıralama
- Eser detay penceresi, 2–4 eser karşılaştırma (cm² fiyatı dahil)
- Sanatçı değer paneli: en düşük / medyan / ortalama / en yüksek açılış fiyatı
- Favoriler (tarayıcıda saklanır)
- Her taramanın fiyatları `auctions.db` içindeki `price_history` tablosunda birikir

## Otomatik güncelleme
`.github/workflows/daily.yml` her gün 06:00 (İstanbul) çalışır: siteleri tarar, `index.html`'i oluşturur, `auctions.db`'yi depoya geri işler ve GitHub Pages'e yayınlar. Actions sekmesinden "Run workflow" ile elle de çalıştırılabilir.

## Yerelde çalıştırma
```bash
./refresh.sh            # tara + index.html oluştur
python3 server.py 8000  # http://localhost:8000
```
Python 3 standart kütüphanesi dışında bağımlılık yoktur.

## Sınırlar
Güncel pey tutarları sitelerde canlı yüklendiği için toplanmaz; fiyatlar açılış / Hemen Al fiyatlarıdır. Veriler sitelerden alındığı gibidir.
