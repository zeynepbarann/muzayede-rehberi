# 16/22 Müzayede Rehberi

Türkiye'deki çevrimiçi müzayede sitelerindeki devam eden eserleri tek yerde toplayan, aranabilir galeri.

**Canlı site:** https://zeynepbarann.github.io/muzayede-rehberi/

## Kaynaklar
nefsmuzayede, dedemuzayede, anatoliamuzayede, kassanat, turkartproject, uxmuzayede, ranasartgallery, galeriberlin, kalamismuzayede, aysilmuzayede, nisartgallery (MüzayedeApp altyapısı), artvela, sanatsalmuzayede, artam, MüzayedeApp portalındaki sanat müzayedeleri, ve kullanıcıların eklediği bağlantılar (`sources.json`). Yalnızca herkese açık sayfalar kullanılır; giriş yapılmaz.

## Bağlantı ekleme
Sitedeki **+ / Bağlantı ekle** formuna bir **müzayede evi**, tek bir **müzayede** veya tek bir **eser** bağlantısı yapıştırın. Form, bu depoda `kaynak` etiketli bir GitHub issue'su açar (istemcide token yoktur); GitHub'da **Create**'e basmanız yeterli.

Issue açılınca `.github/workflows/add-link.yml` hemen çalışır: `add_sources.py --json` sayfayı tarar (önce MüzayedeApp altyapısı, sonra bilinen kazıyıcılar, sonra JSON-LD/OpenGraph), eserleri doğrudan `data/lots.json`'a ekler, `sources.json` / `data/sources.json` / `index.html`'i günceller, commit'ler, sonucu issue'ya yazar ve başarılıysa kapatır. Site birkaç dakika içinde güncellenir; açık sayfa yeni eserler gelince haber verir. Yalnızca depo sahibi ve ortak çalışanların açtığı issue'lar işlenir. Bağlantı Actions sekmesinden (**Run workflow**) elle de eklenebilir.

Tek eser bağlantıları (`kind: "product"`) o evin diğer eserlerinin yerine geçmez, yanlarına eklenir. Günlük tarama (`refresh.sh`) önce `git pull` yapar ve eklenen tüm bağlantıları yeniden tarar.

## Özellikler
- Genel arama (eser, sanatçı, ev, etiket, Lebriz sergi/galeri)
- Yalın filtre çubuğu (ev, bitiş, fiyat, teknik) ve “Daha fazla filtre”
- Birleşik sanatçı adları (yazım/büyük-küçük harf/tarih/kısaltma); elle düzeltmeler `artist_aliases.json`
- Favori sanatçılar: tüm sanatçılar (canlı, geçmiş, Lebriz) aranarak eklenir; henüz eseri olmayan bir ad da eklenebilir. Ana sayfa varsayılan olarak yalnızca onları gösterir. Genel aramada da ☆ ile eklenebilir.
- Altın-siyah tema (varsayılan koyu; ◐ ile açık tema)
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
python3 add_sources.py --json --url https://www.ornek.com/   # auctions.db olmadan doğrudan data/*.json'a ekle
```
Python 3 standart kütüphanesi dışında bağımlılık yoktur (`gh` yalnızca issue işlemek için gerekir).

## Sınırlar
Güncel pey tutarları çoğu sitede canlı yüklendiği için her zaman toplanamaz. Veriler sitelerden alındığı gibidir.
