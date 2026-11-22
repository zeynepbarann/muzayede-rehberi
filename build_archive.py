#!/usr/bin/env python3
"""One light index of every work in the archive, for the Arşiv page: live lots, finished auctions and Lebriz catalogues.

Writes
  data/archive.json       what a grid card needs, one short row per work (loaded when Arşiv opens)
  data/archive_text.json  normalised description text per row, same order (loaded only when someone searches)

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


def image_name(u):
    if not u:
        return ""
    e = img_ext(u)
    return img_key(u) + ("" if e == "jpg" else "." + e)


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
    for p in sorted(glob.glob(os.path.join(DATA, "lebriz_catalog", "*.json"))):
        with open(p, encoding="utf8") as f:
            c = json.load(f)
        name = names.get(c.get("id")) or c.get("name")
        if not name:
            continue
        for w in c.get("works") or []:
            usable = w.get("i") and w.get("z") is not None and (w["z"] == 0 or w["z"] >= 100)
            if not usable and not w.get("t"):
                continue
            y = re.match(r"\d{4}", w.get("y") or "")
            add(name, "Lebriz", int(y.group(0)) * 100 + 1 if y else 0, 0, " ".join(v for v in (w.get("t"), w.get("k"), w.get("s")) if v), 2,
                image_name(w["i"]) if usable else "", w.get("c") or "", w["i"] if usable else "")
    rows.sort(key=lambda r: (not r[0][6], -r[0][2], r[0][5] != 1))   # pictures first, newest first
    src = [sum(1 for r in rows if r[0][5] == s) for s in (0, 1, 2)]
    meta = {"v": 1, "works": len(rows), "with_images": sum(1 for r in rows if r[0][6]), "past": src[0], "live": src[1], "lebriz": src[2],
            "A": A, "H": H, "T": [t for _, t in TECHS], "R": [r[0] for r in rows]}
    for name, obj in (("archive.json", meta), ("archive_text.json", [r[1] for r in rows])):
        tmp = os.path.join(DATA, name + ".tmp")
        with open(tmp, "w", encoding="utf8") as f:
            json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, os.path.join(DATA, name))
    print("archive: %d works (%d finished, %d on sale, %d Lebriz), %d with images, %d artists" % (len(rows), src[0], src[1], src[2], meta["with_images"], len(A)))


if __name__ == "__main__":
    build()
    sys.exit(0)
