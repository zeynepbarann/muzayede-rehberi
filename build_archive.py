#!/usr/bin/env python3
"""One light index of every work in the archive, for the Arşiv page: live lots, finished auctions and Lebriz catalogues.

Writes
  data/archive.json       what a grid card needs, one short row per work (loaded when Arşiv opens)
  data/archive_text.json  normalised description text per row, same order (loaded only when someone searches)
  data/archive_artists.json  one short row per artist name, so the artist lists open without the full index:
                          [name, works, works with a picture, cover bucket name, cover address when it has no bucket name]
  data/img/<xx>.json      bucket name -> original picture address, split by the first two letters of the name; the page reads
                          one small file only when a picture is not in the bucket yet

Row: [artist, house, yyyymm, price, tech*4+size, source, image, id, lebriz image URL]
  artist/house/tech are indexes into the "A", "H" and "T" lists; source 0 finished, 1 on sale, 2 Lebriz
  image is the bucket name (img_key, plus ".ext" when not jpg); the page builds the image door address from it

Standard library only. Run after shard_past.py:  python3 build_archive.py
"""
import glob, json, os, re, sys
import shard_past as S
from mirror_images import img_key, img_ext

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")

# same rules, same order as TECHS in template.html
TECHS = [(r"(tuval|tuyb|t\.u\.y\.b).*(yagli|y\.b)|(yagli ?boya|yagliboya).*tuval|\btuyb\b", "Tuval üzerine yağlıboya"),
         (r"(tuval).*akrilik|akrilik.*tuval|\btuab\b", "Tuval üzerine akrilik"), (r"duralit|sunta|mdf|panel|karton|ahsap uzeri", "Pano/duralit üzerine"),
         (r"minyatur", "Minyatür"), (r"\bhat\b|hattat|celi|sulus|talik|kufi|\blevha\b|hilye", "Hat"), (r"ebru", "Ebru"),
         (r"serigrafi|litografi|gravur|\bbaski\b|ofset|linol|agac baski|edisyon|\bed\b", "Baskı"), (r"heykel|bronz|polyester|mermer|bust\b", "Heykel"),
         (r"fotograf", "Fotoğraf"), (r"(kagit|kuyb|k\.u\.y\.b).*(suluboya|sulu boya)|suluboya|sulu boya", "Suluboya"), (r"guaj", "Guaj"), (r"pastel", "Pastel"),
         (r"karakalem|kursun kalem|rapido|murekkep", "Desen / mürekkep"), (r"kagit|kuyb", "Kağıt üzerine"), (r"akrilik", "Akrilik"), (r"yagli ?boya|yagliboya", "Yağlıboya"),
         (r"kolaj|karisik teknik", "Karışık teknik"), (r"seramik|porselen|cini", "Seramik / porselen"), (r"\bhali\b|kilim", "Halı / kilim"), (r"gumus|bronz obje|sahan|tepsi", "Obje")]
TECH_RX = [re.compile(r) for r, _ in TECHS]
NUM = r"(\d{1,4}(?:[.,]\d{1,2})?)"
SIZE_RX = re.compile(NUM + r"\s*(?:cm)?\s*[x×X*]\s*" + NUM, re.I)


def tech_of(s):
    for i, r in enumerate(TECH_RX):
        if r.search(s):
            return i + 1
    return 0


def size_of(d):
    m = SIZE_RX.search(d or "")
    if not m:
        return 0
    a = float(m.group(1).replace(",", ".")) * float(m.group(2).replace(",", "."))
    return 0 if a <= 0 or a > 4e6 else 1 if a < 1600 else 2 if a < 6400 else 3


def ym(s):
    m = re.match(r"(\d{4})-(\d{2})", s or "")
    return int(m.group(1)) * 100 + int(m.group(2)) if m else 0


ORIGINALS = {}


def image_name(u):
    if not u:
        return ""
    e = img_ext(u)
    name = img_key(u) + ("" if e == "jpg" else "." + e)
    ORIGINALS[name] = u
    return name


def write_artists(A, rows, meta):
    per = {}
    for row, _ in rows:
        e = per.setdefault(row[0], [A[row[0]], 0, 0, "", ""])
        e[1] += 1
        if row[6]:
            e[2] += 1
            if not e[3]:
                e[3] = row[6]
                e[4] = row[8] if len(row) > 8 else ""
    out = {k: meta[k] for k in ("v", "works", "with_images", "past", "live", "lebriz")}
    out["N"] = [e if e[4] else e[:4] if e[3] else e[:3] for e in per.values() if e[0]]
    tmp = os.path.join(DATA, "archive_artists.json.tmp")
    with open(tmp, "w", encoding="utf8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, os.path.join(DATA, "archive_artists.json"))


def write_originals(rows):
    """Where each picture came from, for the ones the page cannot find in the bucket yet."""
    parts = {}
    for r, _ in rows:
        if r[6] and len(r) < 9 and r[6] in ORIGINALS:
            parts.setdefault(r[6][:2], {})[r[6]] = ORIGINALS[r[6]]
    folder = os.path.join(DATA, "img")
    os.makedirs(folder, exist_ok=True)
    for p in glob.glob(os.path.join(folder, "*.json")):
        if os.path.basename(p)[:-5] not in parts:
            os.remove(p)
    for k, v in parts.items():
        with open(os.path.join(folder, k + ".json"), "w", encoding="utf8") as f:
            json.dump(v, f, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def build():
    A, H, Ai, Hi, rows = [], [], {}, {}, []

    def ix(lst, idx, v):
        v = v or ""
        if v not in idx:
            idx[v] = len(lst)
            lst.append(v)
        return idx[v]

    def add(artist, site, date, price, text, source, image, rid, lb_url=""):
        n = S.norm(text)
        rows.append(([ix(A, Ai, artist), ix(H, Hi, site), date, int(price or 0), tech_of(" " + n + " ") * 4 + size_of(text), source, image, rid] + ([lb_url] if lb_url else []), n))

    seen = set()
    with open(os.path.join(DATA, "lots.json"), encoding="utf8") as f:
        for l in json.load(f)["lots"]:
            seen.add((l["site"], str(l["lot_id"])))
            im = (l.get("images") or [""])[0]
            add(l.get("artist") or "", l["site"], ym(l.get("end_date")), l.get("current_bid") or l.get("start_price") or l.get("estimate"),
                " ".join(x for x in (l.get("description"), l.get("title") if not l.get("description") else "", l.get("auction"), l.get("category")) if x), 1, image_name(im), str(l["lot_id"]))
    for x in S.merged_past():
        k = (x.get("site"), str(x.get("lot_id")))
        if k in seen:
            continue
        seen.add(k)
        add(x.get("artist") or "", x.get("site"), ym(x.get("end_date")), x.get("last_bid") or x.get("start_price") or x.get("estimate_min"),
            " ".join(v for v in (x.get("description"), x.get("auction")) if v), 0, image_name(x.get("image")), str(x.get("lot_id")))
    names = {}
    try:
        with open(os.path.join(DATA, "lebriz_index.json"), encoding="utf8") as f:
            names = {a["id"]: a["n"] for a in json.load(f)["artists"]}
    except Exception:
        pass
    in_catalog = set()
    for p in sorted(glob.glob(os.path.join(DATA, "lebriz_catalog", "*.json"))):
        with open(p, encoding="utf8") as f:
            c = json.load(f)
        name = names.get(c.get("id")) or c.get("name")
        if not name:
            continue
        for w in c.get("works") or []:
            m = re.search(r"iName=([^&]+)", w.get("i") or "", re.I)
            if m:
                in_catalog.add((c.get("id"), m.group(1).lower()))
            usable = w.get("i") and w.get("z") is not None and (w["z"] == 0 or w["z"] >= 100)
            if not usable and not w.get("t"):
                continue
            y = re.match(r"\d{4}", w.get("y") or "")
            add(name, "Lebriz", int(y.group(0)) * 100 + 1 if y else 0, 0, " ".join(v for v in (w.get("t"), w.get("k"), w.get("s")) if v), 2,
                image_name(w["i"]) if usable else "", w.get("c") or "", w["i"] if usable else "")
    # the other surviving Lebriz pictures: exhibition works, old auction lots, artist works outside the catalogue pages
    used = set()
    for p in sorted(glob.glob(os.path.join(DATA, "lebriz_more", "*.json")), key=lambda x: os.path.basename(x)[0] != "e"):
        g = os.path.basename(p)[:-5]
        with open(p, encoding="utf8") as f:
            recs = json.load(f)
        for w in recs:
            if w["u"] in used or (w.get("a"), w["n"]) in in_catalog:
                continue
            used.add(w["u"])
            d = re.match(r"\d{2}\.(\d{2})\.(\d{4})", w.get("d") or "")
            add(w.get("an") or "", w.get("g") or "Lebriz", int(d.group(2)) * 100 + int(d.group(1)) if d else 0, 0,
                " ".join(v for v in (w.get("t"), w.get("k"), w.get("s"), w.get("et"), w.get("g"), w.get("c")) if v), 2, image_name(w["u"]), g + "/" + w["n"], w["u"])
    # works cut from printed exhibition catalogues (data/books): the picture is already in the bucket under its own key
    book_index = {}
    for p in sorted(glob.glob(os.path.join(DATA, "books", "*.json"))):
        if os.path.basename(p) == "index.json":
            continue
        with open(p, encoding="utf8") as f:
            bk = json.load(f)
        book_index[S.akey(bk["artist"])] = os.path.basename(p)[:-5]
        by = {b["id"]: b for b in bk["books"]}
        for w in bk["works"]:
            b = by[w["b"]]
            y = re.match(r"\d{4}", w.get("y") or b.get("y") or "")
            add(bk["artist"], "Katalog: " + b["t"] + " (" + b["y"] + ")", int(y.group(0)) * 100 + 1 if y else 0, 0,
                " ".join(v for v in (w.get("k"), w.get("s"), b["t"], b.get("pub")) if v), 2, w["i"], "bk:" + w["id"])
    if book_index:
        with open(os.path.join(DATA, "books", "index.json"), "w", encoding="utf8") as f:
            json.dump(book_index, f, ensure_ascii=False, separators=(",", ":"))
    rows.sort(key=lambda r: (not r[0][6], -r[0][2], r[0][5] != 1))   # pictures first, newest first
    src = [sum(1 for r in rows if r[0][5] == s) for s in (0, 1, 2)]
    meta = {"v": 1, "works": len(rows), "with_images": sum(1 for r in rows if r[0][6]), "past": src[0], "live": src[1], "lebriz": src[2],
            "A": A, "H": H, "T": [t for _, t in TECHS], "R": [r[0] for r in rows]}
    for name, obj in (("archive.json", meta), ("archive_text.json", [r[1] for r in rows])):
        tmp = os.path.join(DATA, name + ".tmp")
        with open(tmp, "w", encoding="utf8") as f:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, os.path.join(DATA, name))
    write_originals(rows)
    write_artists(A, rows, meta)
    print("archive: %d works (%d finished, %d on sale, %d Lebriz), %d with images, %d artists" % (len(rows), src[0], src[1], src[2], meta["with_images"], len(A)))


if __name__ == "__main__":
    build()
    sys.exit(0)
