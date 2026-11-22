#!/usr/bin/env python3
"""Split finished-auction records into one small file per artist, so the site
does not have to download the whole archive to show one artist.

Reads   data/past.json, data/past_archive.json, data/past_archive_mapp.json
        (merged in that order, first record wins per site|lot_id — the same rule
        as loadPast() in template.html)
Writes  data/artist/<slug>.json   records of one artist, in merged order
        data/artist_index.json    {"artists": {key: [slug, count, cover]}, "alson": {...}}
                                  cover = image URL of the artist's most recent record with an
                                  image (left out when there is none)
        data/house_index.json     per auction house: past record count, past auction names,
                                  first image, latest end date (for the houses list and search,
                                  which would otherwise need the full files)

Artists are grouped exactly the way the page groups them (lbMatch()/akey() in
template.html, which use data/artists.json names+variants and the Lebriz index):
  key "lb:<id>"   every record whose artist name resolves to that Lebriz artist
  key "k:<akey>"  every record with that normalised name, when the name itself
                  does not resolve to a Lebriz artist
"alson" lists extra shards for the lot "Değer" panel, which compares by plain
normalised name (norm()) and in rare cases needs records from another shard.

Records without an artist are not sharded; house pages still use the full files.
Standard library only. Run after export.py:  python3 shard_past.py
"""
import json, os, re, sys, hashlib, unicodedata, collections

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT = os.path.join(DATA, "artist")
SOURCES = ["past.json", "past_archive.json", "past_archive_mapp.json"]

# ---- ports of the page's JS helpers (keep in sync with template.html) ----
_JS_WS = set("\t\n\x0b\x0c\r \xa0     　﻿") | {chr(c) for c in range(0x2000, 0x200b)}
_TR = str.maketrans({"I": "ı", "İ": "i"})
_COMB = re.compile("[̀-ͯ]")
_PAREN = re.compile(r"\([^\n\r  ]*?\)")
_QUOTE = re.compile("[`'’ʼ]")
_DIGITS = re.compile(r"[0-9]+")
_cat = unicodedata.category

def js_str(v):
    if v is None: return "null"
    if v is True: return "true"
    if v is False: return "false"
    return str(v)

def norm(s):
    """norm() in template.html: Turkish lower-case, strip accents and punctuation."""
    s = (s or "").replace("İ", "i").translate(_TR).lower().replace("ı", "i")
    s = _COMB.sub("", unicodedata.normalize("NFD", s))
    s = "".join(c if (c not in _JS_WS and _cat(c)[0] in "LN") else " " for c in s)
    return " ".join(x for x in s.split(" ") if x)

def akey(s):
    """akey() in template.html: norm without (…) parts, apostrophes and digits."""
    s = norm(_QUOTE.sub("", _PAREN.sub(" ", s or "")))
    return " ".join(x for x in _DIGITS.sub(" ", s).split(" ") if x)

def lev(a, b, mx):
    if abs(len(a) - len(b)) > mx: return mx + 1
    p = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        c = [i]; mn = i
        for j in range(1, len(b) + 1):
            v = min(p[j] + 1, c[j - 1] + 1, p[j - 1] + (a[i - 1] != b[j - 1]))
            c.append(v)
            if v < mn: mn = v
        if mn > mx: return mx + 1
        p = c
    return p[len(b)]

class Matcher:
    """lbMatch() in template.html. Returns the Lebriz artist id (as str) or None."""
    def __init__(self, artists_json, lebriz_index):
        self.by_name = {}                      # AR.byN: later entries win, like the page
        for a in (artists_json or {}).get("artists") or []:
            for v in [a.get("n")] + list(a.get("v") or []):
                self.by_name[v] = a
        self.ids = set(); self.by_k = {}; self.by_k2 = {}
        for a in (lebriz_index or {}).get("artists") or []:
            aid = js_str(a["id"]); self.ids.add(aid); n = a.get("n") or ""
            for nm in [n] + [m[1:-1] for m in _PAREN.findall(n)]:
                k = akey(nm)
                if not k: continue
                self.by_k.setdefault(k, aid)
                k2 = " ".join(w for w in k.split(" ") if len(w) > 1)
                lst = self.by_k2.setdefault(k2, [])
                if aid not in lst: lst.append(aid)
        self.by_len = collections.defaultdict(list)
        for k in self.by_k: self.by_len[len(k)].append(k)
        self.has_lb = bool(self.ids)
        self._kc = {}; self._nc = {}

    def by_key(self, k):
        """The name-only part of lbMatch (depends on akey alone)."""
        if k in self._kc: return self._kc[k]
        a = None
        if k and len(k) > 2:
            a = self.by_k.get(k)
            if not a:
                c = self.by_k2.get(" ".join(w for w in k.split(" ") if len(w) > 1))
                if c and len(c) == 1: a = c[0]
            if not a and len(k) >= 9:
                h = [x for d in (-1, 0, 1) for x in self.by_len.get(len(k) + d, ()) if lev(x, k, 1) <= 1]
                if len(h) == 1: a = self.by_k[h[0]]
        self._kc[k] = a
        return a

    def match(self, name):
        if not name: return None
        if name in self._nc: return self._nc[name]
        rec = self.by_name.get(name); a = None
        if rec and rec.get("lb") and js_str(rec["lb"]) in self.ids: a = js_str(rec["lb"])
        elif self.has_lb: a = self.by_key(akey(name))
        self._nc[name] = a
        return a

    def group(self, name):
        """Shard key the page will ask for when it shows this artist name."""
        a = self.match(name)
        return "lb:" + a if a else "k:" + akey(name)

# ---- file names ----
_ASCII = re.compile(r"[^a-z0-9]+")
def slug_for(key):
    if key.startswith("lb:") and re.fullmatch(r"[A-Za-z0-9_-]{1,40}", key[3:]):
        return "lb-" + key[3:].lower() if key[3:].lower() == key[3:] else "lb-" + key[3:].lower() + "-" + hashlib.sha1(key.encode("utf8")).hexdigest()[:8]
    body = key.split(":", 1)[1]
    s = _ASCII.sub("-", body).strip("-")[:60].strip("-")
    # plain ASCII names keep a readable file name; anything lossy gets a short hash so names stay unique
    if not s or s.replace("-", " ") != body:
        s = (s + "-" if s else "") + hashlib.sha1(key.encode("utf8")).hexdigest()[:8]
    return "a-" + s

def load(name, default):
    p = os.path.join(DATA, name)
    if not os.path.exists(p): return default
    with open(p, encoding="utf8") as f: return json.load(f)

def merged_past():
    """Same merge as loadPast(): past.json first, then the archives, first key wins."""
    out, seen = [], set()
    for i, name in enumerate(SOURCES):
        for x in load(name, []) or []:
            k = js_str(x.get("site")) + "|" + js_str(x.get("lot_id"))
            if i and k in seen: continue      # past.json itself is taken whole, like the page does
            seen.add(k); out.append(x)
    return out

def house_summary(past):
    """What houses() in template.html derives from the full past list, per site, in first-seen order."""
    out = {}
    for x in past:
        h = out.setdefault(js_str(x.get("site")), {"p": 0, "pa": [], "img": None, "last": ""})
        h["p"] += 1
        a = x.get("auction")
        if a and a not in h.setdefault("_s", set()): h["_s"].add(a); h["pa"].append(a)
        if not h["img"] and x.get("image"): h["img"] = x["image"]
        if (x.get("end_date") or "") > h["last"]: h["last"] = x.get("end_date") or ""
    for h in out.values(): h.pop("_s", None)
    return out

def cover(recs):
    """Image of the artist's most recent record that has one (first wins on equal dates); None if no images."""
    best = None
    for x in recs:
        if x.get("image") and (best is None or (x.get("end_date") or "") > (best.get("end_date") or "")): best = x
    return best["image"] if best else None

def write_if_changed(path, text):
    data = text.encode("utf8")
    try:
        with open(path, "rb") as f:
            if f.read() == data: return False
    except OSError: pass
    tmp = path + ".tmp"
    with open(tmp, "wb") as f: f.write(data)
    os.replace(tmp, path)
    return True

def build(quiet=False):
    past = merged_past()
    m = Matcher(load("artists.json", {}), load("lebriz_index.json", {}))
    shards = collections.defaultdict(list)     # key -> records (merged order)
    home = {}                                  # norm(name) -> set of shard keys holding those records
    skipped = 0
    for x in past:
        name = x.get("artist")
        if not name or not isinstance(name, str): skipped += 1; continue
        k = akey(name); lb = m.match(name); keys = []
        if lb: keys.append("lb:" + lb)
        # the page shows a name-only group when the name does not resolve to Lebriz; that group
        # is everything with the same akey, including records another spelling ties to Lebriz
        if not m.by_key(k) or not m.has_lb: keys.append("k:" + k)
        for key in keys: shards[key].append(x)
        home.setdefault(norm(name), set()).add(keys[0])

    slugs = {}
    for key in shards:
        s = slug_for(key)
        if s in slugs.values(): s += "-" + hashlib.sha1(key.encode("utf8")).hexdigest()[:8]
        slugs[key] = s

    os.makedirs(OUT, exist_ok=True)
    wrote = total = 0; biggest = (0, "", "")
    for key, recs in shards.items():
        text = json.dumps(recs, ensure_ascii=False, separators=(",", ":"))
        wrote += write_if_changed(os.path.join(OUT, slugs[key] + ".json"), text)
        n = len(text.encode("utf8")); total += n
        if n > biggest[0]: biggest = (n, slugs[key] + ".json", key)
    keep = {s + ".json" for s in slugs.values()}
    removed = 0
    for f in os.listdir(OUT):
        if f.endswith((".json", ".tmp")) and f not in keep:
            os.remove(os.path.join(OUT, f)); removed += 1

    # extra shards for the "Değer" panel: records with the same norm() that live outside
    # the shard(s) the page fetches for that normalised name
    alson = {}
    for c, keys in home.items():
        extra = sorted(keys - {m.group(c)})
        if extra: alson[c] = extra
    index = {"v": 1, "records": len(past) - skipped,
             "artists": {k: [slugs[k], len(shards[k])] + ([cover(shards[k])] if cover(shards[k]) else []) for k in sorted(shards)},
             "alson": alson}
    itext = json.dumps(index, ensure_ascii=False, separators=(",", ":"))
    write_if_changed(os.path.join(DATA, "artist_index.json"), itext)
    htext = json.dumps({"v": 1, "houses": house_summary(past)}, ensure_ascii=False, separators=(",", ":"))
    write_if_changed(os.path.join(DATA, "house_index.json"), htext)
    stats = {"records": len(past), "no_artist": skipped, "shards": len(shards), "bytes": total,
             "index_bytes": len(itext.encode("utf8")), "house_index_bytes": len(htext.encode("utf8")), "largest": biggest, "wrote": wrote, "removed": removed}
    if not quiet:
        print(f"shards: {len(shards)} files, {total/1e6:.1f} MB from {len(past)} records "
              f"({skipped} without artist, kept only in the full files); index {stats['index_bytes']/1e3:.0f} kB, house index {stats['house_index_bytes']/1e3:.0f} kB")
        print(f"largest: {biggest[1]} {biggest[0]/1e3:.0f} kB ({len(shards[biggest[2]])} records); "
              f"{wrote} written, {removed} stale removed")
    return stats

if __name__ == "__main__":
    build(quiet="--quiet" in sys.argv)
