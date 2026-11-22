#!/usr/bin/env python3
"""Finished art auctions of the houses listed on muzayede.app, read from each house's own site into data/past_archive_mapp.json.

muzayede.app lists the auctions and sends each one to the house that runs it (galamuzayede.com, kuzgun.art, ...). Only art auctions
are kept. An auction already read is skipped, so a daily run only adds what has ended since. It pauses between requests, says who it
is, and leaves a house alone for the rest of the run the moment that house refuses.

  python3 app_houses_pull.py [--minutes 20] [--limit 1] [--dry]
"""
import html, http.cookiejar, json, os, re, sys, time, urllib.error, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "past_archive_mapp.json")
LIST = "https://www.muzayede.app"
UA = "16-22-archive/1.0"
GAP = 1.5
ART = re.compile(r"resim|sanat|tablo|panay|fine art|güler|dino|çağdaş|klasik")
NOT_ART = re.compile(r"plak|nümismatik|numismatik|pırlanta|elmas|saat|mutfak|mutvak|depo")


class Refused(Exception):
    pass


def low(s):
    return (s or "").replace("İ", "i").replace("I", "ı").lower()


def text(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).replace("\xa0", " ").strip()


def opener():
    o = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    o.addheaders = [("User-Agent", UA), ("Accept-Language", "tr-TR,tr;q=0.9")]
    return o


def get(o, url):
    time.sleep(GAP)
    try:
        with o.open(url, timeout=40) as r:
            return r.geturl(), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 429):
            raise Refused("%s answered %d" % (urllib.parse.urlparse(url).netloc, e.code))
        raise


def listed(o):
    _, page = get(o, LIST + "/muzayede-arsivleri.html")
    out = []
    for c in re.split(r'(?=<div class="col-sm-6 col-xs-12 text-center brand_image_item">)', page)[1:]:
        h = re.search(r'href="(/[^"/]+\.html)"', c)
        t = re.search(r'class="brand_title">(.*?)</h3>', c, re.S)
        d = re.search(r"Son Tarihi\s*:\s*(\d\d)/(\d\d)/(\d{4})\s+(\d\d:\d\d)", text(c))
        n = re.search(r"Toplam\s*:\s*(\d+)\s*Lot", text(c))
        if not (h and t and d):
            continue
        name = text(t.group(1))
        if ART.search(low(name)) and not NOT_ART.search(low(name)):
            out.append({"path": h.group(1), "name": name, "end": "%s-%s-%s %s" % (d.group(3), d.group(2), d.group(1), d.group(4)), "total": int(n.group(1)) if n else 0})
    return out


def parse(page, site, a, brand, seen):
    out = []
    for b in re.split(r'(?=<div id="product_id_)', page)[1:]:
        pid = re.match(r'<div id="product_id_(\d+)', b).group(1)
        if pid in seen:
            continue
        seen.add(pid)
        t = re.search(r'<a href="([^"]+)"[^>]*class="product_title"[^>]*>(.*?)</a>', b, re.S)
        title = text(t.group(2)) if t else ""
        desc = re.search(r'class="p_desc">(.*?)</span>', b, re.S)
        desc = text(desc.group(1)) if desc else ""
        img = re.search(r'data-src="([^"]+)"', b)
        lot = re.search(r"Lot No:\s*(\d+)", b)
        price = re.search(r'class="p_price"[^>]*>\s*([\d.,]+)', b)
        v = int(re.sub(r"\D", "", price.group(1)) or 0) if price else 0
        named = bool(title) and len(title.split()) <= 4 and not re.search(r"\d", title)
        out.append({"site": site, "lot_id": pid, "aid": brand, "lot_no": lot.group(1) if lot else "", "artist": title if named else "",
                    "description": desc if named and desc else " ".join(x for x in (title, desc) if x), "start_price": v or None, "estimate_min": None,
                    "last_bid": None, "bid_count": 0, "auction": a["name"], "end_date": a["end"], "url": html.unescape(t.group(1)) if t else "",
                    "image": html.unescape(img.group(1)) if img else None})
    return out


def read(o, a):
    """(site, brand, lots) of one auction on the house's own site."""
    final, _ = get(o, LIST + a["path"])
    f = urllib.parse.urlparse(final)
    brand = urllib.parse.quote((urllib.parse.parse_qs(f.query).get("brand") or [urllib.parse.unquote(f.path.strip("/"))])[0], safe="/.-_")
    base = "%s://%s" % (f.scheme, f.netloc)
    site = f.netloc.replace("www.", "")
    h = opener()                      # the house keeps the chosen auction in a session, so paging needs its cookie
    _, page = get(h, "%s/%s" % (base, brand))
    seen, lots = set(), []
    lots += parse(page, site, a, brand[:-5], seen)
    for n in range(2, 80):
        if a["total"] and len(lots) >= a["total"]:
            break
        _, page = get(h, "%s/%s?page=%d" % (base, brand, n))
        new = parse(page, site, a, brand[:-5], seen)
        if not new:
            break
        lots += new
    return site, brand[:-5], lots


def main(argv):
    minutes = float(argv[argv.index("--minutes") + 1]) if "--minutes" in argv else 20
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else 0
    dry = "--dry" in argv
    stop = time.time() + minutes * 60
    with open(OUT, encoding="utf8") as f:
        have = json.load(f)
    known = {(x.get("site"), str(x.get("lot_id"))) for x in have}
    names = {x.get("auction") for x in have if x.get("aid") and not str(x.get("aid")).isdigit()}
    o = opener()
    todo = [a for a in listed(o) if a["name"] not in names]
    print("app houses: %d art auctions to read" % len(todo), flush=True)
    added, refused, count = [], set(), 0
    for a in todo[:limit] if limit else todo:
        if time.time() > stop:
            print("time budget reached; the next run continues"); break
        try:
            site, _, lots = read(o, a)
        except Refused as e:
            print("  refused, skipping:", e, flush=True); refused.add(str(e)); continue
        except Exception as e:
            print("  could not read %s: %s" % (a["name"], e), flush=True); continue
        new = [x for x in lots if (x["site"], x["lot_id"]) not in known]
        known.update((x["site"], x["lot_id"]) for x in new)
        added += new; count += 1
        print("  %s · %s: %d of %s lots" % (site, a["name"], len(lots), a["total"] or "?"), flush=True)
    if dry:
        for x in added[:5]:
            print(json.dumps({k: x[k] for k in ("site", "lot_no", "artist", "description", "end_date", "image")}, ensure_ascii=False)[:300])
    elif added:
        tmp = OUT + ".tmp"
        with open(tmp, "w", encoding="utf8") as f:
            json.dump(have + added, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, OUT)
    print("app houses: %d auctions read, %d lots %s, %d refusals" % (count, len(added), "found (dry run)" if dry else "added", len(refused)))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:])
