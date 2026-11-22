#!/usr/bin/env python3
"""Every other artwork picture of Lebriz that the Internet Archive kept: exhibition works, old auction lots, and artist works
that appear in no catalogue page we could read.

Lists all archived pictures (two requests), keeps the largest copy of each at 100px or more, attaches what the archive still
knows (exhibition, gallery, date, artist, title, technique, size) and writes small files the site loads on demand:
  data/lebriz_more/a<artist>.json   works of one artist
  data/lebriz_more/e<exhibition>.json   works of one exhibition
  data/lebriz_more/m<auction>.json   lots of one old auction catalogue
Artist portraits, press documents, gallery logos and catalogue covers are left out: they are not artworks.

  python3 lebriz_more.py [--cdx listing1.txt listing2.txt]    # reuse saved listings instead of asking the archive
"""
import collections, glob, html, json, os, re, sys, urllib.parse
import lebriz_pull as LP
from shard_past import norm

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT = os.path.join(DATA, "lebriz_more")
MIN_SIZE = 100


def param(o, name):
    m = re.search(rf"[?&]{name}=([^&]*)", o, re.I)
    return urllib.parse.unquote(m.group(1)) if m else ""


def listings(argv):
    if "--cdx" in argv:
        for p in argv[argv.index("--cdx") + 1:]:
            with open(p, encoding="utf8", errors="replace") as f:
                yield from f
        return
    for host in ("lebrizimages.com", "lebrizimages.net"):
        q = urllib.parse.urlencode([("url", host + "/imageHandler"), ("matchType", "prefix"), ("filter", "statuscode:200"),
                                    ("filter", "mimetype:image/.*"), ("fl", "timestamp,original,length")])
        yield from LP.net("https://web.archive.org/cdx/search/cdx?" + q, timeout=300).decode("utf8", "replace").splitlines()


def name_of(url):
    return param(html.unescape(url), "iName").lower()


def build(argv):
    best = {}
    for line in listings(argv):
        r = line.strip().split(" ")
        if len(r) < 2:
            continue
        o = html.unescape(r[1])
        name, path, amt = param(o, "iName"), param(o, "iPath").strip("/"), param(o, "iResizeAmount")
        m = re.match(r"(artst|sergi|muzdb)/(\d+)$", path, re.I)
        if not m or not name or not amt.isdigit() or "-ph-" in name.lower():
            continue
        kind, folder = m.group(1).lower(), int(m.group(2))
        if kind == "muzdb" and not re.match(r"k\d", name, re.I):
            continue
        z = int(amt) or 9999
        k = (kind, folder, name.lower())
        if k not in best or (z, r[0]) > (best[k][0], best[k][1]):
            best[k] = (z, r[0], r[1])
    with open(os.path.join(DATA, "lebriz_index.json"), encoding="utf8") as f:
        idx = json.load(f)
    names = {a["id"]: a["n"] for a in idx["artists"]}
    for p in glob.glob(os.path.join(DATA, "lebriz_catalog", "*.json")):
        with open(p, encoding="utf8") as f:
            c = json.load(f)
        if c.get("name"):
            names.setdefault(c["id"], c["name"])
    ex = {e["id"]: e for e in idx["exhibitions"]}
    known = {}   # (exhibition, picture name) -> artist and labels, from the records of artists' exhibitions
    with open(os.path.join(DATA, "lebriz_artists.json"), encoding="utf8") as f:
        for aid, v in json.load(f).items():
            for w in v.get("works") or []:
                if w.get("e") and w.get("i"):
                    known[(w["e"], name_of(w["i"]))] = (int(aid), w)
    by_name = sorted(((norm(n), i) for i, n in names.items() if len(norm(n)) > 6), key=lambda x: -len(x[0]))

    def solo(title):
        t = " " + norm(title or "") + " "
        hit = {i for n, i in by_name if " " + n + " " in t}
        return hit.pop() if len(hit) == 1 else None
    groups, tiny, seen = collections.defaultdict(list), 0, {"artst": 0, "sergi": 0, "muzdb": 0}
    for (kind, folder, name), (z, ts, url) in sorted(best.items()):
        if z < MIN_SIZE:
            tiny += 1
            continue
        rec = {"n": name, "u": f"https://web.archive.org/web/{ts}im_/{url}", "z": 0 if z == 9999 else z}
        seen[kind] += 1
        if kind == "artst":
            if folder not in names:
                seen[kind] -= 1
                continue
            rec["a"] = folder
            groups["a%d" % folder].append(rec)
        elif kind == "sergi":
            e = ex.get(folder) or {}
            aid, w = known.get((folder, name), (None, {}))
            aid = aid or solo(e.get("t"))
            rec.update({k: v for k, v in (("e", folder), ("et", e.get("t")), ("g", e.get("g")), ("c", e.get("c")), ("d", e.get("s")),
                                          ("a", aid), ("t", w.get("t")), ("k", w.get("k")), ("s", w.get("s"))) if v})
            groups["e%d" % folder].append(rec)
            if aid:
                groups["a%d" % aid].append(rec)
        else:
            rec["m"] = folder
            groups["m%d" % folder].append(rec)
    os.makedirs(OUT, exist_ok=True)
    for p in glob.glob(os.path.join(OUT, "*.json")):
        if os.path.basename(p)[:-5] not in groups:
            os.remove(p)
    for g, recs in groups.items():
        for r in recs:
            r.setdefault("an", names.get(r.get("a"), "")) if r.get("a") else None
        with open(os.path.join(OUT, g + ".json"), "w", encoding="utf8") as f:
            json.dump(recs, f, ensure_ascii=False, separators=(",", ":"))
    print("lebriz_more: %d artist pictures, %d exhibition pictures, %d auction lots; %d files; %d left out as under %dpx" % (seen["artst"], seen["sergi"], seen["muzdb"], len(groups), tiny, MIN_SIZE))


if __name__ == "__main__":
    build(sys.argv[1:])
