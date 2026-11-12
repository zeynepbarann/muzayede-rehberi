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
- Dört sekme: **Favorilerim** (seçilen sanatçıların satıştaki eserleri + kaydedilen eserler), **Keşfet** (tüm eserler), **Müzayede Evleri** (evler + eklenen bağlantılar), **Arşiv** (Lebriz)
- Keşfet'te tek bir **Filtrele** paneli: anahtarlar (favori sanatçılarım, Hemen Al, arşivde olanlar), bitiş ve fiyat seçenekleri, ev, teknik, sanatçı, etiketler; etkin filtreler kaldırılabilir çipler olarak görünür
- Sade kartlar (görsel, sanatçı, fiyat, kalan süre); eser ve sanatçı sayfaları sekmeli (Eser / Değer / Sanatçı / Arşiv; Şu an satışta / Değer / Biyografi / Sergiler)
- ⚙ menüsü: koyu tema, açılışta Favorilerim, kartlarda açıklama; Bağlantı ekle; Nasıl çalışır?
- İlk ziyarette 3 adımlık rehber + sık sorulanlar; ⓘ ile kısa açıklamalar; her boş ekranda ne yapılacağı yazar
- Genel arama (eser, sanatçı, ev, etiket, Lebriz sergi/galeri); sanatçılar ☆ ile favorilere eklenebilir
- Birleşik sanatçı adları (yazım/büyük-küçük harf/tarih/kısaltma); elle düzeltmeler `artist_aliases.json`
- Karşılaştırma (en fazla 4 eser), altın-siyah tema; telefonda alt sekmeler ve yüzen Filtrele düğmesi
- Ayarlar ve favoriler yalnızca tarayıcıda (localStorage) tutulur

## Otomatik güncelleme
`./refresh.sh` her gün: `add_sources.py` → `scrape.py` → (Pazartesi veya `--lebriz`) `lebriz.py` → `lebriz_export.py` → `export.py`.

**Günlük commit'e dahil edilmesi gerekenler:**
- `index.html`
- `data/` (`lots.json`, `past.json`, `artists.json`, `sources.json`, `lebriz_*.json`, `past_archive_mapp.json`, `history_log.json`)
- yeni dosyalar dahil: `data/` altındaki her şey (`git add data/`)
- kökteki `sources.json` (yeni bağlantı eklendiyse)

**Commit edilmemesi gerekenler:** `auctions.db` (artık gitignore'da; kutu üzerinde kalır), `*.png`, `*.log`, `lebriz_cache/`, `raw_*.html`.

## Geçmiş müzayedeler
- `data/past.json`: günlük taramanın canlıyken gördüğü, artık bitmiş eserler (Ekim 2026'dan beri).
- `data/past_archive.json`: Artam'ın 2024'ten beri biten müzayedeleri (`history.py`, GitHub Action, her ayın 1'i). Artam çekiç fiyatını yalnızca üyelerine gösterdiği için tahmin değeri vardır.
- `data/past_archive_mapp.json`: MüzayedeApp altyapılı evlerin biten müzayedeleri (`history_mapp.py`, `refresh.sh` içinde her gün en fazla ~40 dk, kaldığı yerden devam eder). Bu siteler GitHub sunucularını engellediği için yalnızca günlük taramanın çalıştığı makinede çalışır. Ne bulduğu `data/history_log.json`'a yazılır.

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
