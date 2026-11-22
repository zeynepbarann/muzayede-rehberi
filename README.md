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
- **Bütün site bir galeri:** sayfanın zemini kesintisiz bir galeri duvarıdır; her eser çerçevesiyle (altın, abanoz, ceviz, beyaz, bronz pervaz; kâğıt işlerde paspartu, çerçevesiz satılanlarda ince tuval çerçevesi) bu duvara asılır, altında müze etiketi durur. Telefonda alt sekme çubuğu galerinin ahşap zeminidir
- **Dokunmatik hareket:** kaydırdıkça duvar bir silindir gibi döner (CSS scroll-driven animations), eserler telinde hafifçe sallanır; telefonu eğince (jiroskop) ya da parmağınızı ekranda gezdirince çerçeveler o yöne yatar ve camları ışığı yakalar. `prefers-reduced-motion` açıksa hareket kapanır. iOS jiroskop iznini ilk dokunuşta sorar
- **3B Galeri / salon** (`#galeri`): duvardaki bir esere dokununca o eserin karşısında, yuvarlak bir salonun ortasında durursunuz. O an bakılan liste (Keşfet filtreleri, Favorilerim, sanatçı, ev ya da arama sonucu) salonun duvarlarına asılıdır; parmağınızla sağa-sola çevirirsiniz, savurunca birkaç eser birden döner. Öndeki esere dokununca yakınlaştırma açılır; alttaki etiket kâğıdını yukarı çekince ayrıntılar gelir; **Tur** kendiliğinden gezer. Duvardaki boy, ilanda ölçü varsa gerçek ölçüyle orantılıdır. Yalnızca CSS 3D kullanır, ek kütüphane yoktur
- **Katlanabilir telefonlar:** tarayıcı menteşeyi bildirirse (viewport segments) duvar bir yarıda, etiket/ayrıntılar öbür yarıda durur; yarı katlı duruşta (device posture) ekran ikiye bölünür; açık Fold gibi geniş ekranlarda duvar solda, ayrıntılar sağdadır
- **Görünüm:** site basılı bir müzayede kataloğu gibi okunur: kâğıt zemin, siyah mürekkep, ince çizgiler, numaralı lotlar. Açılış sayfasında iki kapı vardır: **Müzayedeler** ve **Kataloglar**; favoriler **Koleksiyon** sekmesindedir. Varsayılan tema açıktır
- **Kataloglar** (`#kataloglar`, `#katalog=<sanatçı>`): her sanatçı için arşivdeki bütün kayıtlardan (satıştaki eserler + biten müzayedeler, yıl yıl) kendiliğinden derlenen yatay albüm. Rafta sanatçının bir eserini taşıyan yatay kapaklar; içeride her açılım tek eserdir: bir sayfada görsel, öbüründe katalog kaydı; bölüm başlarında o yılın küçük görselleri. Dik ekranda albüm üstten ciltlidir ve yapraklar yukarı çevrilir; geniş ekranda yandan ciltlidir. Katlanabilir telefonda cilt menteşeye, sayfalar ekranın iki yarısına oturur
- **Veri nerede duruyor:** asıl kayıt, taramanın çalıştığı makinedeki `auctions.db` (SQLite; depoda yok). Site bunu `data/*.json` olarak okur (GitHub Pages, statik). Görseller saklanmaz, müzayede evlerinin sunucularına bağlanır. Favoriler ve ayarlar yalnızca tarayıcıdadır
- Sade kartlar (görsel, sanatçı, fiyat, kalan süre); eser ve sanatçı sayfaları sekmeli (Eser / Değer / Sanatçı / Arşiv; Şu an satışta / Değer / Biyografi / Sergiler)
- ⚙ menüsü: koyu tema, açılışta Favorilerim, kartlarda açıklama; Bağlantı ekle; Nasıl çalışır?
- İlk ziyarette 3 adımlık rehber + sık sorulanlar; ⓘ ile kısa açıklamalar; her boş ekranda ne yapılacağı yazar
- Genel arama (eser, sanatçı, ev, etiket, Lebriz sergi/galeri); sanatçılar ☆ ile favorilere eklenebilir
- **Müzayede Evleri**'nde ev arama (ad ya da müzayede adı; sıralama: en çok eser, A–Z, son müzayede). Her evin kendi sayfası var (`#house=<site>`): şu an müzayededeki eserleri ve geçmiş müzayedeleri, müzayede müzayede kaydırılabilir sıralar halinde; sayfa içinde arama
- Birleşik sanatçı adları (yazım/büyük-küçük harf/tarih/kısaltma); elle düzeltmeler `artist_aliases.json`
- Karşılaştırma (en fazla 4 eser), altın-siyah tema; telefonda alt sekmeler ve yüzen Filtrele düğmesi
- Ayarlar ve favoriler yalnızca tarayıcıda (localStorage) tutulur

## Otomatik güncelleme
`./refresh.sh` her gün: `add_sources.py` → `scrape.py` → (Pazartesi veya `--lebriz`) `lebriz.py` → `lebriz_export.py` → `export.py` → `shard_past.py`.

**Günlük commit'e dahil edilmesi gerekenler:**
- `index.html`
- `data/` (`lots.json`, `past.json`, `artists.json`, `sources.json`, `lebriz_*.json`, `past_archive_mapp.json`, `history_log.json`)
- yeni dosyalar dahil: `data/` altındaki her şey (`git add data/`)
- kökteki `sources.json` (yeni bağlantı eklendiyse)

**Commit edilmemesi gerekenler:** `auctions.db` (artık gitignore'da; kutu üzerinde kalır), `*.png`, `*.log`, `lebriz_cache/`, `raw_*.html`.

## Geçmiş müzayedeler
- `data/artist/<slug>.json`, `data/artist_index.json`, `data/house_index.json`: biten müzayede kayıtlarının sanatçı başına küçük dosyaları ve ev özeti (`shard_past.py`, aşağıdaki üç dosyadan üretilir). Sanatçı sayfası, katalog ve eserdeki "Değer" paneli yalnızca ilgili sanatçının dosyasını indirir; dosya yoksa tam arşive döner. Ev sayfaları hâlâ tam arşivi kullanır.
- `data/past.json`: günlük taramanın canlıyken gördüğü, artık bitmiş eserler (Ekim 2026'dan beri).
- `data/past_archive.json`: Artam'ın 2024'ten beri biten müzayedeleri (`history.py`, GitHub Action, her ayın 1'i). Artam çekiç fiyatını yalnızca üyelerine gösterdiği için tahmin değeri vardır.
- `data/past_archive_mapp.json`: MüzayedeApp altyapılı evlerin biten müzayedeleri (`history_mapp.py`, `refresh.sh` içinde her gün en fazla ~40 dk, kaldığı yerden devam eder). Bu siteler GitHub sunucularını engellediği için yalnızca günlük taramanın çalıştığı makinede çalışır. Ne bulduğu `data/history_log.json`'a yazılır.
- Bir MüzayedeApp evinde müzayede bağlantısı bulunamazsa günlük tarama `data/debug/<ev>.json`'a sayfanın kısa bir özetini (başlık, bağlantılar, denenen adresler) yazar; okuyucu o eve göre buradan düzeltilir. Bulunca dosya silinir.

## Görsellerin saklanması (özel Google bucket)
Müzayede evleri satış bitince görselleri silebildiği için görseller kendi bucket'ımıza (`16-22`) kopyalanır. Bucket herkese kapalı kalır; görselleri yalnızca **görsel kapısı** (`imgproxy/`, Cloud Run) verir.
- `mirror_images.py`: `data/` içindeki bütün görsel adreslerini bir kez indirir ve bucket'a `i/<anahtar>.<uzantı>` adıyla yükler. Anahtar, özgün adresin özetidir (`img_key`); bu yüzden hiçbir yerde eşleme tablosu tutulmaz. Kaldığı yeri `mirror_state.json`'da hatırlar (depoya girmez). `refresh.sh` her gün en fazla 30 dakika çalıştırır; ilk toplu kopya için bir kez süresiz çalıştırın. Yalnızca yükleme yetkili bir servis hesabı anahtarı ister (`GCS_KEY`, varsayılan `~/.config/16-22-uploader.json`); anahtar depoya konmaz. `--dry-run` anahtarsız sayım yapar.
- `imgproxy/main.py`: `GET /i/<anahtar>.<uzantı>?u=<özgün adres>`. Görsel bucket'ta varsa onu verir; henüz kopyalanmadıysa ve `u` gerçekten o anahtara denk geliyorsa özgün adrese yönlendirir. `ALLOWED_REFERERS` ile yalnızca kendi sitenizden gelen istekler kabul edilir.
- Site tarafı: `template.html` içindeki `IMG_BASE` boşken hiçbir şey değişmez. Kapının adresi yazılınca bütün görseller oradan istenir; kapı yanıt vermezse görsel özgün adresten yüklenir.

## Bulutta günlük tarama (kimsenin bilgisayarı açık olmak zorunda değil)
`cloudjob/` bir Cloud Run **job**'ıdır; Cloud Scheduler her sabah çalıştırır. Her çalışmada depoyu klonlar, veritabanını (`state/auctions.db`) ve görsel kopyalama durumunu özel bucket'tan alır, `refresh.sh` ile aynı adımları yürütür (yeni bağlantılar, günlük tarama, biten müzayedeler, görsel kopyalama, dışa aktarma, sanatçı parçaları), sonucu denetler, `Daily refresh <tarih>` olarak push eder ve veritabanını bucket'a geri koyar.
- Kod çalışma anında klonlandığı için depodaki bir betiği değiştirmek job'ı yeniden kurmayı gerektirmez.
- İlk çalışmada bucket'ta veritabanı yoktur; `seed_db.py` onu `data/lots.json` ve `data/past.json`'dan yeniden kurar. Elinizde eski `auctions.db` varsa `gs://16-22/state/auctions.db` olarak yükleyin, o kullanılır.
- Güvenlik: biten eser sayısı %10'dan fazla düşerse ya da canlı eser kalmazsa hiçbir şey yayımlanmaz.
- Erişim: bucket için job'ın kendi servis hesabı (anahtar dosyası yok); GitHub'a push için Secret Manager'daki `GH_TOKEN` (yalnızca bu depoda Contents: read/write).
- `JOB_MODE=probe` yalnızca müzayede sitelerinin buluttan yanıt verip vermediğini dener; `DRY_RUN=1` her şeyi çalıştırır ama push etmez.

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
