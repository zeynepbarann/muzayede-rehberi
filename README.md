# 16/22 Müzayede Rehberi

Türkiye'deki çevrimiçi müzayede sitelerindeki devam eden eserleri tek yerde toplayan, aranabilir galeri.

**Canlı site:** https://zeynepbarann.github.io/muzayede-rehberi/

## Kaynaklar
nefsmuzayede, dedemuzayede, anatoliamuzayede, kassanat, turkartproject, uxmuzayede, ranasartgallery, galeriberlin, kalamismuzayede, aysilmuzayede, nisartgallery (MüzayedeApp altyapısı), artvela, sanatsalmuzayede, artam, MüzayedeApp portalındaki sanat müzayedeleri, ve kullanıcıların eklediği bağlantılar (`sources.json`). Yalnızca herkese açık sayfalar kullanılır; giriş yapılmaz.

## Bağlantı ekleme
Sitedeki **+ / Bağlantı ekle** formuna bir müzayede veya müzayede evi adresi yapıştırın. Form, `zeynepbarann/muzayede-rehberi` deposunda `kaynak` etiketli bir GitHub issue'su açar (istemcide token yoktur). Günlük tarama (`add_sources.py`) açık issue'ları okur, URL'yi `sources.json` listesine ekler, sayfayı tarar (önce MüzayedeApp altyapısı, sonra bilinen kazıyıcılar, sonra JSON-LD/OpenGraph), sonucu issue'ya yorum olarak yazar ve başarılıysa kapatır.

## Özellikler
- Genel arama (eser, sanatçı, ev, etiket, Lebriz sergi/galeri)
- Yalın filtre çubuğu (ev, bitiş, fiyat, teknik) ve “Daha fazla filtre”
- Birleşik sanatçı adları (yazım/büyük-küçük harf/tarih/kısaltma); elle düzeltmeler `artist_aliases.json`
- Favori sanatçılar: ana sayfa varsayılan olarak yalnızca onları gösterir
- Eser detayı, karşılaştırma, Lebriz sanatçı sayfası, değer paneli

## Otomatik güncelleme
`./refresh.sh` her gün: `add_sources.py` → `scrape.py` → (Pazartesi veya `--lebriz`) `lebriz.py` → `lebriz_export.py` → `export.py`.

**Günlük commit'e dahil edilmesi gerekenler:**
- `index.html`
- `data/` (`lots.json`, `past.json`, `artists.json`, `sources.json`, `lebriz_*.json`)
- kökteki `sources.json` (yeni bağlantı eklendiyse)

**Commit edilmemesi gerekenler:** `auctions.db` (artık gitignore'da; kutu üzerinde kalır), `*.png`, `*.log`, `lebriz_cache/`, `raw_*.html`.

## Yerelde çalıştırma
```bash
./refresh.sh            # tara + index.html oluştur
python3 server.py 8000  # http://localhost:8000
python3 add_sources.py --url https://www.ornek.com/
```
Python 3 standart kütüphanesi dışında bağımlılık yoktur (`gh` yalnızca issue işlemek için gerekir).

## Sınırlar
Güncel pey tutarları çoğu sitede canlı yüklendiği için her zaman toplanamaz. Veriler sitelerden alındığı gibidir.
