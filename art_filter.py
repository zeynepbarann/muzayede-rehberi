#!/usr/bin/env python3
"""Tell artworks from accessories and antiques in auction listings.

Nothing is deleted: build_archive.py writes the listings this module rejects to data/hidden.json and the site leaves them out.
Paintings, works on paper, artist prints, calligraphy, sculpture and signed art photography stay. Jewellery, watches, lighters,
pens, silver, porcelain, glass, textiles, toys, coins, books, postcards, documents, records and furniture go.

A listing is only hidden on evidence: when nothing in it says what it is, it stays.
"""
import re
from shard_past import norm


def rx(words):
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(words.split()) + r")(?![a-z0-9])")


# the house's own category, when it has one
ART_CATEGORY = {"resim", "tablo", "tablolar", "hat", "hat yazi", "cerceveli", "cercevesiz", "heykel", "gravur", "fotograf", "eser", "devrim erbil serigrafi"}
UNSURE_CATEGORY = {"", "suleymaniye"}

# the listing opens by naming a painting medium: long biographies further down may mention books and magazines
OPENS_AS_ART = re.compile(r"tuval|yagli ?boya|sulu ?boya|\bguaj|akrilik|kara ?kalem|murekkep|kagit uzer|karton uzer|duralit|pastel|karisik teknik|fine art baski")

# books and periodicals, which can talk about painting without being one
PRINTED = re.compile(r"prestij kitap|hardcover|\d+ sayfa|sayfa sayisi|yayinevi|yayinlari|sergi katalogu|ansiklopedi|kartpostal|dergisi|le petit journal|"
                     r"kabin foto|cabinet card|isyeri karti|nadir tasra|ilk baski|\bsayi \d")
BOOK_MARK = re.compile(r"/\s*kitap\s*/", re.I)   # needs the raw text: norm() removes the slashes
BOOK_NAME = re.compile(r"\bkitabi$")             # "Semih Balcioglu Kitabi" in the name field

# collectible brands and characters, whatever they are made of
BRAND = re.compile(r"\b(?:kaws|lalique|formula 1|disney|pop mart|leblon delienne|funko|medicom|bearbrick|labubu|tubbz|die ?cast|del prado|james bond|"
                   r"nintendo|donald duck|mickey|minnie)\b")

# what the work is made with: the strongest sign of art, even when a vase or a clock is what it depicts
MEDIUM = re.compile(r"tuval|\bt u y b\b|\btuyb\b|\bkuyb\b|yagli ?boya|akrilik|sulu ?boya|kuru boya|\bguaj|pastel|kara ?kalem|kursun kalem|rapido|murekkep|"
                    r"kagit uzer|karton uzer|mukavva uzer|duralit|sunta|\bmdf\b|ahsap uzer|pano uzer|panel uzer|bez uzer|litograf|serigraf|gravur\b|linol|giclee|"
                    r"\bbaski\b|printed on|art print|kolaj|karisik teknik|\bebru|minyatur|\bdesen\b|\beskiz\b|karikatur|hilye|levha|hat yazi|\bceli\b|sulus|talik|ketebe|"
                    r"\bheykel|goblen tablo|eczacibasi|seramik pano|seramik panel|seramik uzer|\bmermer")
# a photograph counts as art when it is signed or certified, or by a photographer the market collects
PHOTO = re.compile(r"fotograf")
PHOTO_ART = re.compile(r"imzali|sertifika|gofreli|fine art|karanlik oda|ara guler")

# history and paper ephemera, usually named in the artist field
HISTORY = re.compile(r"\btarihi?\b|osmanlica|\bosmanli\b|\bww1\b|dunya savasi|sehadetname|\bermeni|padisahlar serisi|milli mucadele|mesrutiyet|\bnazi\b|\bptt\b|\bberat\b")

# things, by name
OBJECT = rx("""saat saati saatler saatleri kostek cakmak cakmagi zippo ronson dupont colibri rolex omega longines swatch seiko tissot cartier
dolmakalem montblanc parker kalemlik divit hokka hokkasi yuzuk kolye kolyesi bileklik bilezik kupe kupesi bros mucevher mucevheri pirlanta
tespih tesbih canta cantasi cuzdan cuzdani pudriyer pudriye tabakasi gozluk gozlugu kravat baston bastonu sapka mendil
vazo vazosu surahi surahisi ibrik ibrigi tabagi tepsi tepsisi fincan fincani kase kasesi kadeh bardak bardagi sahan sefertasi semaver cezve kupa
catal bicak kasik kasigi samdan samdani sekerlik sekerligi cerezlik sosluk sebil gulabdan buhurdan mangal ayna aynasi avize avizesi abajur lamba lambasi aplik
biblo biblosu jardinyer saksi kaspo kutu kutusu kutusunda kutulu sandik sandigi sehpa sehpasi konsol koltuk sandalye kanepe paravan
porselen seramik kristal opalin murano meissen limoges christofle sevres herend rosenthal capodimonte beykoz bohem kutahya vitray
halisi kilim yastik peskir yaglik bohca cepken kaftan kumas tekstil dantel parfum sise sisesi fuzyon gumusten
oyuncak oyuncagi maket matruska polystone polyresin seti takimi
banknot banknotu sikke madalya madalyon rozet kartvizit kartvizitlik telgraf telgrafi telefon
mektup mektubu harita haritasi ferman senet belge belgesi gazete afis afisi takvim salname diploma
kitap plak plagi gramofon radyo daktilo durbun durbunu barometre pusula hancer tufek tabanca
lule tutun tombak ikebana""")
OBJECT_PHRASE = re.compile(r"fotograf makine|dolma kalem|kol dugme|kagit para|altin kaplama|gumus kaplama|24 k kaplama|tugrali gumus|poz veren|souvenir de|el oyma|degirmeni|hamam tasi|altinvarak cerceve|pink ph?ant")
# words that are also names: they only count in the description, never in the artist field
NAME_LIKE = rx("gumus altin bakir bronz sedef elmas zumrut yakut inci kemer kemeri tabak tabaka hali")


def listing_is_art(x):
    """is_artwork() for a record of lots.json or the past files."""
    d = x.get("description") or ""
    return is_artwork(x.get("artist") or "", d, "" if d else x.get("title") or "", x.get("category") or "")


def is_artwork(artist="", description="", title="", category=""):
    cat = norm(category)
    a, d = norm(artist), norm(" ".join(x for x in (description, title) if x))
    text = (a + " " + d).strip()
    book = BOOK_MARK.search(description or "")
    if OPENS_AS_ART.search(d[:90]) and not book:
        return True
    if book or PRINTED.search(text) or BOOK_NAME.search(a) or BRAND.search(text):
        return False
    if cat in ART_CATEGORY:
        return True
    if cat not in UNSURE_CATEGORY:   # the house filed it under something that is not art
        return False
    if not a.startswith("anonim") and (" / " in (artist or "") or HISTORY.search(a)):   # "Askeri Tarih / ...": how sellers of paper ephemera title a listing
        return False
    if MEDIUM.search(text) or (PHOTO.search(text) and PHOTO_ART.search(text)):
        return True
    if OBJECT.search(text) or OBJECT_PHRASE.search(text) or PHOTO.search(text):
        return False
    return not NAME_LIKE.search(d)
