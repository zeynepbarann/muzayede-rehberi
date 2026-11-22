#!/usr/bin/env python3
"""Pull an artist's Lebriz catalogue ("Bütün Katalog") from the Internet Archive.

lebriz.com closed in 2023; its pages survive as Wayback Machine snapshots. The importer
(lebriz.py) only keeps exhibition works. This script reads every archived catalogue page
(artist.aspx?section=130 with its pageNo / periodID variants) for the given artists and
writes data/lebriz_catalog/<artistID>.json, which the artist page shows in its
"Lebriz kataloğu" tab. Only pages the archive kept can be read, so a catalogue may be partial.

Usage:
  python3 lebriz_pull.py --ids 123,456 [--summary out.md]
  python3 lebriz_pull.py --event $GITHUB_EVENT_PATH [--summary out.md]   # issue "Lebriz: …" / workflow_dispatch
"""
import os, re, sys, json, html, time, urllib.request, urllib.parse, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "lebriz_catalog")
WB = "https://web.archive.org/web/"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36"
MAX_PAGES = int(os.environ.get("LEBRIZ_MAX_PAGES", "400"))
_last = [0.0]


def net(url, timeout=90):
    err = None
    for i in range(5):
        wait = float(os.environ.get("LEBRIZ_GAP", "1.2")) - (time.time() - _last[0])
        if wait > 0: time.sleep(wait)
        _last[0] = time.time()
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=timeout) as r:
                b = r.read()
            if b"Temporarily Offline" in b[:3000]: raise RuntimeError("archive offline")
            return b
        except urllib.error.HTTPError as e:
            if e.code == 404: return b""
            err = e
        except Exception as e:
            err = e
        time.sleep(4 * (i + 1))
    raise RuntimeError(f"fetch failed {url}: {err}")


T = lambda s: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()
def wbimg(u, ts): return f"{WB}{ts[:4]}im_/{html.unescape(u)}" if u else ""


def snapshots(aid):
    """All archived artist.aspx URLs for this artist (one per distinct URL, largest copy kept)."""
    q = urllib.parse.urlencode([("url", "lebriz.com/pages/artist.aspx"), ("matchType", "prefix"),
                                ("filter", "statuscode:200"), ("filter", rf"original:(?i).*[?&]artistid={aid}(&.*)?$"),
                                ("fl", "timestamp,original,length")])
    rows = [l.split(" ") for l in net("https://web.archive.org/cdx/search/cdx?" + q, timeout=300).decode("utf8", "replace").splitlines()]
    if not rows:   # the filtered search sometimes comes back empty; a plain prefix finds the usual URL form
        q = urllib.parse.urlencode([("url", f"lebriz.com/pages/artist.aspx?artistID={aid}"), ("matchType", "prefix"),
                                    ("filter", "statuscode:200"), ("fl", "timestamp,original,length")])
        rows = [l.split(" ") for l in net("https://web.archive.org/cdx/search/cdx?" + q, timeout=300).decode("utf8", "replace").splitlines()]
        rows = [r for r in rows if len(r) > 1 and re.search(rf"[?&]artistid={aid}(&|$)", r[1], re.I)]
    best = {}
    for r in rows:
        if len(r) < 3 or not r[2].isdigit(): continue
        key = re.sub(r"^https?://(www\.)?", "", r[1].lower())
        if key not in best or int(r[2]) > int(best[key][2]): best[key] = r
    return list(best.values())


def param(url, name):
    m = re.search(rf"[?&]{name}=([^&]*)", url, re.I)
    return m.group(1) if m else ""


WORK_RE = [
    # exhibition-style thumbnails: <input type="image" title="Eser kodu : CODE  title size technique" src=…>
    re.compile(r'<input[^>]*type="image"[^>]*>', re.I),
    re.compile(r'<img[^>]*>', re.I),
]


SIZE = re.compile(r"\d+(?:[.,]\d+)?\s*[x×X]\s*\d+(?:[.,]\d+)?(?:\s*[x×X]\s*\d+(?:[.,]\d+)?)?\s*cm", re.I)
def clean(w):
    """Split Lebriz's one-string label ("Title\\r\\rTechnique\\r89 x 127 cm") into title / technique / size / year."""
    raw = " \n ".join(x for x in (w.get("t"), w.get("k"), w.get("s")) if x)
    parts = [re.sub(r"\s+", " ", x).strip(" ,-") for x in re.split(r"[\r\n]+", raw)]
    parts = [x for x in parts if x]
    size = next((SIZE.search(x).group(0) for x in parts if SIZE.search(x)), "")
    parts = [SIZE.sub("", x).strip(" ,-") for x in parts]
    parts = [x for x in parts if x]
    title, tech = (parts[0] if parts else ""), ", ".join(parts[1:])
    yr = re.search(r"\b(1[89]\d{2}|20[0-2]\d)\b", raw)
    w.update(t=title, k=tech, s=re.sub(r"\s+", " ", size), y=yr.group(1) if yr else "")
    return w

def lebriz_name(aid):
    try:
        return next((a["n"] for a in json.load(open(os.path.join(HERE, "data", "lebriz_index.json"), encoding="utf8"))["artists"] if a["id"] == aid), None)
    except Exception:
        return None

def parse_works(h, ts, page_url):
    """Return works found on one archived catalogue page."""
    out, seen = [], set()
    for rx in WORK_RE:
        for tag in rx.findall(h):
            attr = lambda a: html.unescape((re.search(rf'\b{a}="([^"]*)"', tag, re.I) or [None, ""])[1])
            txt = (attr("title") or attr("alt")).replace("Detaylı bilgi ve büyük resim için tıklayın", "").strip()
            src = attr("src")
            c = re.match(r"(?:Eser kodu|Work code|Code)\s*:\s*(\S+)\s*(.*)", txt, re.I)
            if not c or not src: continue
            code, rest = c.group(1), c.group(2)
            if code in seen: continue
            seen.add(code)
            out.append(clean({"c": code, "t": rest, "i": wbimg(src, ts), "p": f"{WB}{ts}/{page_url}"}))
        if out: break
    return out


def page_name(h):
    """The artist's name from an archived page title ("lebriz.com - Name"); list pages carry a generic title instead."""
    m = re.search(r"<title[^>]*>\s*lebriz\.com\s*-\s*(.*?)\s*</title>", h, re.I | re.S)
    n = T(m.group(1)) if m else ""
    return n if n and n.lower() not in ("sanatçılar", "artists", "sanatçı", "artist", "ana sayfa", "home") else None


def find_name(snaps):
    for s in sorted(snaps, key=lambda s: (param(s[1], "section") != "100", -int(s[2])))[:5]:
        try:
            n = page_name(net(f"{WB}{s[0]}id_/{s[1]}").decode("utf8", "replace"))
        except Exception:
            continue
        if n: return n
    return None


def parse_thumbs(h, aid, ts, page_url):
    """Cover pages list a work only as a small picture with no label: keep it as a work known by its id."""
    out = {}
    for m in re.finditer(r'src="([^"]*imageHandler[^"]*)"', h, re.I):
        src = html.unescape(m.group(1))
        wt, wid, path = [re.search(rx, src, re.I) for rx in (r"wType=(\d+)", r"wID=(\d+)", r"iPath=/?artst/(\d+)")]
        if wt and wid and path and wt.group(1) == "1" and int(path.group(1)) == aid:
            code = f"a{aid:04d}-{wid.group(1)}"
            out[code] = {"c": code, "t": "", "k": "", "s": "", "y": "", "i": wbimg(src, ts), "p": f"{WB}{ts}/{page_url}"}
    return list(out.values())


IMG_CACHE = os.environ.get("LEBRIZ_IMG_CACHE") or os.path.join(HERE, ".lebriz_images.json")
_images = [None]


def image_map():
    """Every artwork picture the archive kept, largest copy per work: {"artist:work": [timestamp, url, size]}.
    Two listing requests for all of Lebriz, cached for a day, instead of searching artist by artist."""
    if _images[0] is not None:
        return _images[0]
    if os.path.exists(IMG_CACHE) and time.time() - os.path.getmtime(IMG_CACHE) < 86400:
        _images[0] = json.load(open(IMG_CACHE, encoding="utf8"))
        return _images[0]
    best = {}
    for host in ("lebrizimages.com", "lebrizimages.net"):
        q = urllib.parse.urlencode([("url", host + "/imageHandler"), ("matchType", "prefix"), ("filter", "statuscode:200"),
                                    ("filter", "mimetype:image/.*"), ("fl", "timestamp,original")])
        for line in net("https://web.archive.org/cdx/search/cdx?" + q, timeout=300).decode("utf8", "replace").splitlines():
            r = line.split(" ")
            if len(r) < 2: continue
            o = html.unescape(r[1])
            wt, wid, path, amt = [re.search(rx, o, re.I) for rx in (r"wType=(\d+)", r"wID=(\d+)", r"iPath=/?artst/(\d+)", r"iResizeAmount=(\d+)")]
            if not (wid and path and amt) or (wt and wt.group(1) != "1"): continue
            k, z = f"{int(path.group(1))}:{wid.group(1)}", int(amt.group(1)) or 9999
            if k not in best or (z, r[0]) > (best[k][2], best[k][0]): best[k] = [r[0], r[1], z]
    tmp = IMG_CACHE + ".tmp"
    json.dump(best, open(tmp, "w", encoding="utf8"))
    os.replace(tmp, IMG_CACHE)
    _images[0] = best
    return best


def apply_images(works, aid):
    """Use the best surviving copy of each picture, add works known only from their picture, drop works with nothing left."""
    try:
        imgs = image_map()
    except Exception as e:
        print("  image list unavailable:", e, flush=True)
        return works
    pre = f"{aid}:"
    for k, (ts, url, z) in imgs.items():
        if not k.startswith(pre): continue
        code = f"a{aid:04d}-{k[len(pre):]}"
        w = works.setdefault(code, {"c": code, "t": "", "k": "", "s": "", "y": "", "p": ""})
        w["i"], w["z"] = f"{WB}{ts}im_/{url}", (0 if z == 9999 else z)
    for code in list(works):
        w = works[code]
        if "z" not in w: w["i"] = ""
        if not w.get("i") and not w.get("t"): del works[code]
    return works


def pull(aid):
    t0 = time.time()
    snaps = snapshots(aid)
    for wait in (20, 60):   # the archive sometimes answers a listing with nothing when it is busy
        if snaps: break
        time.sleep(wait)
        snaps = snapshots(aid)
    cat = [s for s in snaps if param(s[1], "section") == "130"]
    name, total, series = None, None, {}
    pages = sorted(cat, key=lambda s: ("lang=tr" in s[1].lower(), -int(param(s[1], "pageNo") or 0)), reverse=True)[:MAX_PAGES]
    works, read, empty = {}, 0, 0
    print(f"artist {aid}: {len(snaps)} archived artist pages, {len(cat)} catalogue pages", flush=True)
    for s in pages:
        try:
            b = net(f"{WB}{s[0]}id_/{s[1]}")
        except Exception as e:
            print("  skip", s[1], e, flush=True); continue
        h = b.decode("utf8", "replace")
        if len(b) < 6000 or "bhawkTest" in h: continue
        read += 1
        name = name or page_name(h)
        for m in re.finditer(r'class="rmText">([^<]{2,90}?)\s*\((\d+)\)</span>', h):
            nm, c = T(m.group(1)), int(m.group(2))
            if nm == "Bütün Katalog" or nm.lower() == "all catalogue": total = total or c
            elif not nm.startswith(("Online", "Galeri", "Müzayede")): series[nm] = c
        found = parse_works(h, s[0], s[1])
        per = param(s[1], "periodID")
        for w in found + parse_thumbs(h, aid, s[0], s[1]):
            if per and per != "-1" and "series" not in w: w["sr"] = per
            if w["c"] not in works or (w.get("t") and not works[w["c"]].get("t")): works[w["c"]] = w
        if read % 10 == 0: print(f"  {read} pages read, {len(works)} works", flush=True)
        if time.time() - t0 > 40 * 60: print("  time limit reached for this artist", flush=True); break
    works = apply_images(works, aid)
    name = lebriz_name(aid) or name or find_name(snaps)
    rec = {"id": aid, "name": name, "total": total, "series": series, "pages_archived": len(cat), "pages_read": read,
           "pulled_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "with_images": sum(1 for w in works.values() if w.get("i")), "partial": not snaps, "works": list(works.values())}
    return rec


def ids_from_event(path):
    ev = json.load(open(path, encoding="utf8"))
    it = ev.get("issue") or {}
    text = (it.get("body") or "") + "\n" + (it.get("title") or "")
    if not it: text = (ev.get("inputs") or {}).get("ids") or ""
    m = re.search(r"Lebriz ID[^:]*:\s*([\d,\s]+)", text, re.I)
    return [int(x) for x in re.findall(r"\d+", m.group(1) if m else text)][:40]


def main():
    a = sys.argv[1:]
    ids = []
    if "--ids" in a: ids = [int(x) for x in re.findall(r"\d+", a[a.index("--ids") + 1])]
    if "--event" in a: ids = ids or ids_from_event(a[a.index("--event") + 1])
    summary = a[a.index("--summary") + 1] if "--summary" in a else None
    os.makedirs(OUT, exist_ok=True)
    lines, ok = [], 0
    for aid in dict.fromkeys(ids):
        try:
            rec = pull(aid)
        except Exception as e:
            lines.append(f"- {aid}: hata — {e}"); print("FAIL", aid, e, flush=True); continue
        old = os.path.join(OUT, f"{aid}.json")
        if not rec["works"] and os.path.exists(old):
            lines.append(f"- {rec['name'] or aid}: arşivde okunabilir katalog sayfası bulunamadı (önceki veri korundu)"); continue
        json.dump(rec, open(old, "w", encoding="utf8"), ensure_ascii=False, separators=(",", ":"))
        ok += 1
        lines.append(f"- {rec['name'] or aid}: **{len(rec['works'])} eser** (Lebriz'de toplam {rec['total'] or '?'}; "
                     f"arşivde {rec['pages_archived']} katalog sayfası, {rec['pages_read']} tanesi okundu)")
        print("OK", aid, len(rec["works"]), "works", flush=True)
    body = ("Lebriz kataloğu çekildi:\n\n" if ok else "Lebriz kataloğu çekilemedi:\n\n") + "\n".join(lines or ["- sanatçı numarası bulunamadı"]) + \
           "\n\nSite birkaç dakika içinde güncellenir. Yalnızca Internet Archive'ın sakladığı sayfalar okunabildiği için katalog eksik olabilir."
    if summary: open(summary, "w", encoding="utf8").write(body)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a") as f: f.write(f"ok={'true' if ok else 'false'}\ncount={ok}\n")


if __name__ == "__main__":
    main()
