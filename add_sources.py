#!/usr/bin/env python3
"""Ingest user-submitted auction-house URLs.

Reads open GitHub issues labelled 'kaynak' on zeynepbarann/muzayede-rehberi,
adds each URL to sources.json, scrapes it (MüzayedeApp platform first, then
known scrapers, then a generic HTML/JSON-LD/OpenGraph extractor), comments the
result, and closes the issue on success.

Also re-scrapes every already-added source (called from refresh.sh).

A URL can be a whole auction house, one auction, or a single artwork page.
Single artwork pages (kind "product") are added next to the house's other lots
instead of replacing them.

Usage:
  python3 add_sources.py              # issues + refresh added sources
  python3 add_sources.py --url URL    # add & scrape one URL locally (no issue)
  python3 add_sources.py --dry-run    # process issues but don't comment/close
  python3 add_sources.py --json --event EVENT.json [--summary OUT.md]
  python3 add_sources.py --json --url URL [--summary OUT.md]
      # GitHub Actions mode: no auctions.db; merges the scraped lots straight
      # into data/*.json, sources.json and index.html so the site updates now.
"""
import os, re, sys, json, html, time, shutil, datetime as dt, urllib.request, sqlite3, subprocess, traceback
from urllib.parse import urlparse, urljoin
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "sources.json")
DB = os.path.join(HERE, "auctions.db")
REPO = "zeynepbarann/muzayede-rehberi"
GH = shutil.which("gh") or "/usr/local/bin/gh"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36"

import scrape

def load_sources():
    if not os.path.exists(SRC):
        return {"added": []}
    return json.load(open(SRC, encoding="utf8"))

def save_sources(s):
    tmp = SRC + ".tmp"
    json.dump(s, open(tmp, "w", encoding="utf8"), ensure_ascii=False, indent=2)
    os.replace(tmp, SRC)

def get(url, data=None, tries=3):
    return scrape.get(url, data, tries)

def host_of(url):
    h = urlparse(url).netloc.lower()
    if h.startswith("www."): h = h[4:]
    return h

def normalize_url(url):
    url = (url or "").strip()
    if not url: return ""
    if not re.match(r"^https?://", url, re.I): url = "https://" + url
    p = urlparse(url)
    if not p.netloc: return ""
    return url

URL_RE = re.compile(r"https?://[^\s)\]>'\"<>]+", re.I)

def parse_issue_url(title, body):
    text = (body or "") + "\n" + (title or "")
    # prefer a line after "Kaynak URL"
    m = re.search(r"Kaynak URL:\s*(\S+)", text, re.I)
    if m:
        u = normalize_url(m.group(1))
        if u: return u
    for u in URL_RE.findall(text):
        u = u.rstrip(".,);")
        if "github.com" in u: continue
        u = normalize_url(u)
        if u: return u
    # title may be just a host
    m = re.search(r"(?:Kaynak:\s*)?([a-z0-9.-]+\.[a-z]{2,})", title or "", re.I)
    if m and "github" not in m.group(1).lower():
        return normalize_url(m.group(1))
    return ""

def detect_muzayedeapp(page, url):
    if not page: return False
    if "muzayedeappRemaining" in page or 'id="product-item-' in page or "data-kkp=" in page:
        return True
    if re.search(r"cdn.*cloudfront.*Images/Shop", page) and "/muzayede/" in (page + url):
        return True
    return False

def scrape_generic(url):
    """Best-effort single-page or listing extractor (JSON-LD, OpenGraph, item-like HTML)."""
    page = get(url)
    lots = []
    site = host_of(url)
    # JSON-LD
    for blk in re.findall(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', page, re.S | re.I):
        try:
            data = json.loads(html.unescape(blk))
        except Exception:
            continue
        items = data if isinstance(data, list) else [data]
        extra = []
        for d in items:
            if isinstance(d, dict) and isinstance(d.get("@graph"), list):
                extra.extend(d["@graph"])
        items.extend(extra)
        for d in items:
            if not isinstance(d, dict): continue
            typ = d.get("@type") or ""
            if typ in ("ItemList",):
                for el in d.get("itemListElement") or []:
                    if isinstance(el, dict):
                        it = el.get("item") or el
                        if isinstance(it, dict): items.append(it)
            if typ not in ("Product", "VisualArtwork", "Offer", "Painting", "Sculpture"): continue
            offers = d.get("offers") or {}
            if isinstance(offers, list): offers = offers[0] if offers else {}
            price = scrape.num(str((offers or {}).get("price") or d.get("price") or ""))
            imgs = d.get("image") or []
            if isinstance(imgs, str): imgs = [imgs]
            if isinstance(imgs, dict): imgs = [imgs.get("url")]
            name = d.get("name") or d.get("title") or ""
            artist = ""
            if isinstance(d.get("creator"), dict): artist = d["creator"].get("name") or ""
            elif isinstance(d.get("author"), dict): artist = d["author"].get("name") or ""
            elif isinstance(d.get("creator"), str): artist = d["creator"]
            uid = d.get("sku") or d.get("productID") or d.get("@id") or name
            lots.append(dict(
                site=site, lot_id=str(uid)[:80], lot_no="", title=name, artist=artist or name,
                description=scrape.txt(d.get("description") or ""), category=d.get("category") or "",
                start_price=price, estimate=None, current_bid=None, bid_count=0, currency="TL",
                auction=scrape.txt((re.search(r"<title>([^<]+)", page) or [None, site])[1]),
                auction_type="auction", end_date=None, images=json.dumps([i for i in imgs if i][:8]),
                url=d.get("url") or url))
    if lots:
        return lots, [(site, "jsonld", "JSON-LD", len(lots))], "json-ld", page
    # OpenGraph — single item page
    og = lambda p: (re.search(r'property=["\']og:%s["\'][^>]*content=["\']([^"\']+)' % p, page, re.I)
                    or re.search(r'content=["\']([^"\']+)["\'][^>]*property=["\']og:%s' % p, page, re.I)
                    or [None, ""])[1]
    title = html.unescape(og("title") or ((re.search(r"<title>([^<]+)", page) or [None, ""])[1]))
    image = html.unescape(og("image") or "")
    desc = html.unescape(og("description") or "")
    # listing-like cards: several product/lot links
    hrefs = re.findall(r'href="([^"]+(?:/urun/|/lot/|/eser/|/item/|/product/)[^"]+)"', page, re.I)
    if len(set(hrefs)) >= 3:
        # too shallow to fetch each here except first few would be slow; treat as "needs dedicated scraper"
        return [], [(site, "generic", f"listing-like page ({len(set(hrefs))} item links) but no structured lots", 0)], "generic-listing", page
    if title and (image or desc):
        lots.append(dict(
            site=site, lot_id=re.sub(r"\W+", "-", urlparse(url).path)[:80] or "og",
            lot_no="", title=scrape.txt(title), artist=scrape.txt(title), description=scrape.txt(desc),
            category="", start_price=None, estimate=None, current_bid=None, bid_count=0, currency="TL",
            auction=host_of(url), auction_type="auction", end_date=None,
            images=json.dumps([image] if image else []), url=url))
        return lots, [(site, "og", "OpenGraph", 1)], "opengraph", page
    return [], [(site, "none", "no lots extracted", 0)], "none", page

def kind_of(url, method, lots):
    """'product' for a single artwork page, otherwise 'house' (whole house / auction / listing)."""
    path = urlparse(url).path.strip("/")
    if path and method in ("opengraph", "json-ld") and 0 < len(lots) <= 3:
        return "product"
    return "house"

def scrape_url(url):
    """Return (lots, auctions, method, error)."""
    url = normalize_url(url)
    if not url: return [], [], "", "geçersiz URL"
    host = host_of(url)
    # known built-in scrapers by domain
    known = {
        "artvela.com": scrape.scrape_artvela,
        "sanatsalmuzayede.com": scrape.scrape_sanatsal,
        "artam.com": scrape.scrape_artam,
    }
    try:
        page = get(url if urlparse(url).path not in ("", "/") else "https://" + ("www." + host if not urlparse(url).netloc.startswith("www.") else urlparse(url).netloc) + "/")
    except Exception as e:
        page = ""
        first_err = e
    else:
        first_err = None
    # MüzayedeApp platform (own domain or a /muzayede/ path)
    try:
        if page and detect_muzayedeapp(page, url):
            lots, aucs = scrape.scrape_muzayedeapp("www." + host if not host.startswith("www.") else host)
            return lots, aucs, "muzayedeapp", None
        if host in {h.replace("www.", "") for h in scrape.MUZAYEDEAPP}:
            lots, aucs = scrape.scrape_muzayedeapp("www." + host)
            return lots, aucs, "muzayedeapp", None
        if host in known:
            lots, aucs = known[host]()
            return lots, aucs, "known:" + host, None
        if host == "muzayedeapp.com" or host.endswith(".muzayedeapp.com"):
            # a portal auction URL
            skip = set()
            portal = scrape.scrape_mapp_portal(skip)
            lots, aucs = [], []
            for s, (L, A) in portal.items():
                lots += L; aucs += A
            return lots, aucs, "muzayedeapp-portal", None
        lots, aucs, method, _ = scrape_generic(url)
        return lots, aucs, method, None
    except Exception as e:
        return [], [], "", f"{e}" if not first_err else f"{first_err}"

def upsert_lots(lots, site, replace=True):
    db = sqlite3.connect(DB)
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    db.executescript("""CREATE TABLE IF NOT EXISTS lots(site,lot_id,lot_no,title,artist,description,category,start_price REAL,estimate REAL,current_bid REAL,
      bid_count INT,currency,auction,auction_type,end_date,images,url,scraped_at, PRIMARY KEY(site,lot_id));
    CREATE TABLE IF NOT EXISTS runs(at,site,status,lots,detail);
    CREATE TABLE IF NOT EXISTS price_history(at,site,lot_id,artist,title,description,start_price REAL,estimate REAL,current_bid REAL,bid_count INT,auction,end_date,url,image, PRIMARY KEY(at,site,lot_id));""")
    if replace:
        db.execute("DELETE FROM lots WHERE site=?", (site,))
    for l in lots:
        l = dict(l); l["scraped_at"] = now
        db.execute("INSERT OR REPLACE INTO price_history VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (now, l["site"], l["lot_id"], l["artist"], l["title"], l["description"], l["start_price"],
                    l["estimate"], l["current_bid"], l["bid_count"], l["auction"], l["end_date"], l["url"],
                    (json.loads(l["images"]) or [None])[0]))
        db.execute(f"INSERT OR REPLACE INTO lots({','.join(l)}) VALUES({','.join('?'*len(l))})", list(l.values()))
    db.commit(); db.close()
    return now

def record_run(site, status, n, detail):
    db = sqlite3.connect(DB)
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    db.execute("CREATE TABLE IF NOT EXISTS runs(at,site,status,lots,detail)")
    db.execute("INSERT INTO runs VALUES(?,?,?,?,?)", (now, site, status, n, detail))
    db.commit(); db.close()
    return now

def find_source(data, url, kind):
    """Exact URL first; a house also matches another house record on the same host.
    Single artworks (and failed links of unknown kind) only match their own URL."""
    for s in data["added"]:
        if (s.get("url") or "").rstrip("/") == url.rstrip("/"):
            return s
    if kind == "house":
        for s in data["added"]:
            if s.get("kind") != "product" and (host_of(s.get("url") or "") == host_of(url) or s.get("host") == host_of(url)):
                return s
    return None

def upsert_source(url, issue=None, **kw):
    data = load_sources()
    host = host_of(url)
    kind = kw.get("kind") or ("house" if not urlparse(url).path.strip("/") else "unknown")
    if kind == "unknown": kw.pop("kind", None)
    rec = find_source(data, url, kind)
    if rec is None:
        rec = {"url": url, "host": host, "added_at": dt.date.today().isoformat(), "issue": issue}
        data["added"].append(rec)
    rec["url"] = url
    rec["host"] = host
    if issue and not rec.get("issue"): rec["issue"] = issue
    rec.update(kw)
    save_sources(data)
    return rec

def scrape_and_store(url, issue=None):
    lots, aucs, method, err = scrape_url(url)
    host = host_of(url)
    detail = "; ".join(f"{a[2]} [{a[3]} lots]" for a in aucs) or (err or "no auctions")
    if err:
        now = record_run(host, "fail", 0, str(err))
        rec = upsert_source(url, issue, status="fail", lots=0, detail=str(err), last_run=now, method=method)
        return rec, False, str(err)
    # success even if 0 live lots (house is tracked)
    kind = kind_of(url, method, lots)
    upsert_lots(lots, host, replace=(kind != "product"))
    now = record_run(host, "ok", len(lots), f"{method}: {detail}")
    rec = upsert_source(url, issue, status="ok", lots=len(lots), detail=f"{method}: {detail}", last_run=now, method=method, kind=kind)
    return rec, True, detail

def gh(*args, input=None):
    r = subprocess.run([GH, *args], input=input, text=True, capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or r.stdout.strip() or f"gh {' '.join(args)} failed")
    return r.stdout

def process_issues(dry=False):
    try:
        raw = gh("issue", "list", "--repo", REPO, "--label", "kaynak", "--state", "open",
                 "--json", "number,title,body,url", "--limit", "50")
    except Exception as e:
        print("issue list failed:", e)
        return []
    issues = json.loads(raw or "[]")
    results = []
    for it in issues:
        url = parse_issue_url(it.get("title"), it.get("body"))
        num = it["number"]
        if not url:
            msg = "Bu issue'da taranacak bir URL bulamadım. Lütfen `Kaynak URL: https://…` satırı ekleyin."
            print(f"issue #{num}: no url")
            if not dry:
                gh("issue", "comment", str(num), "--repo", REPO, "--body", msg)
            results.append((num, False, "no url")); continue
        print(f"issue #{num}: scraping {url}")
        rec, ok, detail = scrape_and_store(url, issue=num)
        if ok:
            body = (f"Tarama sonucu: **{rec['lots']} eser** bulundu.\n\n"
                    f"- Kaynak: {url}\n- Yöntem: `{rec.get('method')}`\n- Ayrıntı: {detail}\n\n"
                    f"`sources.json` dosyasına eklendi; sonraki günlük taramalarda güncellenecek.")
        else:
            body = (f"Tarama başarısız oldu.\n\n- Kaynak: {url}\n- Hata: {detail}\n\n"
                    "Issue açık bırakıldı; bir sonraki günlük taramada yeniden denenecek.")
        print(("OK" if ok else "FAIL"), rec["lots"], detail)
        if not dry:
            gh("issue", "comment", str(num), "--repo", REPO, "--body", body)
            if ok: gh("issue", "close", str(num), "--repo", REPO, "--reason", "completed")
        results.append((num, ok, detail))
    return results

def refresh_added(skip_hosts=None):
    skip_hosts = set(skip_hosts or [])
    data = load_sources()
    out = []
    for s in list(data.get("added") or []):
        url = s.get("url")
        if not url or host_of(url) in skip_hosts: continue
        print("refresh", url)
        rec, ok, detail = scrape_and_store(url, issue=s.get("issue"))
        out.append((url, ok, rec["lots"], detail))
        print(("OK" if ok else "FAIL"), rec["lots"], detail)
    return out

# ---------- GitHub Actions mode: merge straight into the static site ----------
DATA = os.path.join(HERE, "data")

def read_json(path, default):
    try:
        return json.load(open(path, encoding="utf8"))
    except Exception:
        return default

def write_json(path, obj, pretty=False):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf8") as f:
        if pretty: json.dump(obj, f, ensure_ascii=False, indent=2)
        else: json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, path)

def canon_artists(new_lots):
    """Give new lots the site's canonical artist names (data/artists.json); add unseen artists."""
    import artists as A
    path = os.path.join(DATA, "artists.json")
    store = read_json(path, {"raw": 0, "canon": 0, "merged": 0, "artists": []})
    by_raw, by_fold = {}, {}
    for rec in store["artists"]:
        for v in [rec["n"], *(rec.get("v") or [])]:
            by_raw.setdefault(v, rec)
            f = A.fold(v)
            if f: by_fold.setdefault(f, rec)
    for l in new_lots:
        raw = (l.get("artist") or "").strip()
        if not raw: continue
        rec = by_raw.get(raw) or by_fold.get(A.fold(raw))
        if rec is None:
            if not A.is_personish(raw): continue
            rec = {"n": raw, "v": [raw], "lb": None, "c": 0}
            store["artists"].append(rec); by_raw[raw] = rec; by_fold[A.fold(raw)] = rec
        if raw not in rec["v"]: rec["v"].append(raw)
        rec["c"] = (rec.get("c") or 0) + 1
        if rec["n"] != raw:
            l["artist_raw"] = raw; l["artist"] = rec["n"]
        if rec.get("lb"): l["lb_id"] = rec["lb"]
    store["canon"] = len(store["artists"])
    write_json(path, store)

def patch_index(sources, count, stamp):
    """Refresh the META block in index.html so browsers fetch the new data files."""
    path = os.path.join(HERE, "index.html")
    page = open(path, encoding="utf8").read()
    k = page.find("const META=")
    if k < 0: return
    k += len("const META=")
    try:
        meta, end = json.JSONDecoder().raw_decode(page, k)
    except Exception:
        return
    meta.update({"updated": stamp, "v": stamp.replace(" ", "T"), "count": count, "sources": sources})
    blob = json.dumps(meta, ensure_ascii=False).replace("</", "<\\/")
    open(path, "w", encoding="utf8").write(page[:k] + blob + page[end:])

def json_add(url, issue=None):
    """Scrape one link and merge it into data/lots.json etc. Returns (ok, record, detail, n_new)."""
    url = normalize_url(url)
    if not url:
        return False, {"url": url, "lots": 0}, "geçersiz URL", 0
    now = dt.datetime.now()
    stamp = now.strftime("%Y-%m-%d %H:%M")
    lots, aucs, method, err = scrape_url(url)
    host = host_of(url)
    detail = "; ".join(f"{a[2]} [{a[3]} lots]" for a in aucs) or (err or "no auctions")
    src = load_sources()
    if err:
        kind = "house" if not urlparse(url).path.strip("/") else "unknown"
        rec = find_source(src, url, kind)
        if rec is None:
            rec = {"url": url, "host": host, "added_at": now.date().isoformat(), "issue": issue}
            src["added"].append(rec)
        rec.update(status="fail", lots=0, detail=str(err), last_run=stamp, method=method)
        if issue and not rec.get("issue"): rec["issue"] = issue
        save_sources(src); write_json(os.path.join(DATA, "sources.json"), src)
        store = read_json(os.path.join(DATA, "lots.json"), {"lots": []})
        patch_index(src["added"], len(store.get("lots") or []), stamp)
        return False, rec, str(err), 0
    kind = kind_of(url, method, lots)
    live = []
    for l in lots:
        l = dict(l)
        if l.get("end_date") and l["end_date"] <= stamp: continue
        imgs = l.get("images")
        l["images"] = json.loads(imgs) if isinstance(imgs, str) else (imgs or [])
        l.pop("currency", None); l.pop("scraped_at", None)
        if (l.get("title") or "") in ("", (l.get("artist") or "") + " - " + (l.get("description") or "")):
            l.pop("title", None)
        l["history"] = [[stamp, l.get("start_price"), l.get("bid_count") or 0]]
        live.append(l)
    canon_artists(live)
    lp = os.path.join(DATA, "lots.json")
    store = read_json(lp, {"updated": stamp, "lots": []})
    old = store.get("lots") or []
    if kind == "product":
        keys = {(l["site"], l["lot_id"]) for l in live}
        drop = lambda l: (l.get("site"), l.get("lot_id")) in keys
    else:
        sites = {l["site"] for l in live} or {host}
        drop = lambda l: l.get("site") in sites
    prev = {(l.get("site"), l.get("lot_id")): l for l in old if drop(l)}
    for l in live:  # keep price history from earlier scrapes
        p = prev.get((l["site"], l["lot_id"]))
        if p and p.get("history"):
            l["history"] = [h for h in p["history"] if h[0] != stamp] + l["history"]
    merged = [l for l in old if not drop(l) and not (l.get("end_date") and l["end_date"] <= stamp)] + live
    merged.sort(key=lambda l: (l.get("end_date") is None, l.get("end_date") or "", l.get("site") or ""))
    store["lots"] = merged; store["updated"] = stamp
    write_json(lp, store)
    rec = find_source(src, url, kind)
    if rec is None:
        rec = {"url": url, "host": host, "added_at": now.date().isoformat(), "issue": issue}
        src["added"].append(rec)
    rec.update(url=url, host=host, kind=kind, status="ok", lots=len(live), detail=f"{method}: {detail}", last_run=stamp, method=method)
    if issue and not rec.get("issue"): rec["issue"] = issue
    save_sources(src); write_json(os.path.join(DATA, "sources.json"), src)
    patch_index(src["added"], len(merged), stamp)
    return True, rec, detail, len(live)

def json_main(args):
    url, issue = None, None
    if "--url" in args:
        url = args[args.index("--url") + 1]
    if "--event" in args:
        ev = read_json(args[args.index("--event") + 1], {})
        it = ev.get("issue") or {}
        if it:
            issue = it.get("number")
            url = parse_issue_url(it.get("title"), it.get("body"))
        elif not url:
            url = ((ev.get("inputs") or {}).get("url") or "").strip()
    summary = args[args.index("--summary") + 1] if "--summary" in args else None
    if not url:
        ok, rec, detail, n = False, {"url": "", "lots": 0}, "Bu istekte taranacak bir URL bulunamadı. `Kaynak URL: https://…` satırı ekleyin.", 0
    else:
        print("scraping", url)
        try:
            ok, rec, detail, n = json_add(url, issue)
        except Exception as e:
            traceback.print_exc()
            ok, rec, detail, n = False, {"url": url, "lots": 0}, f"{type(e).__name__}: {e}", 0
    print(("OK" if ok else "FAIL"), n, detail)
    if ok:
        what = "eser sayfası" if rec.get("kind") == "product" else "kaynak"
        body = (f"Eklendi: **{n} eser** sitede.\n\n- Bağlantı: {url}\n- Tür: {what}\n- Yöntem: `{rec.get('method')}`\n"
                f"- Ayrıntı: {detail[:600]}\n\nSite birkaç dakika içinde güncellenir. Bağlantı günlük taramaya da eklendi.")
    else:
        body = (f"Tarama başarısız oldu.\n\n- Bağlantı: {url or '—'}\n- Hata: {str(detail)[:600]}\n\n"
                "İstek açık bırakıldı; günlük taramada yeniden denenecek.")
    if summary:
        open(summary, "w", encoding="utf8").write(body)
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf8") as f:
            f.write(f"ok={'true' if ok else 'false'}\nlots={n}\nhost={host_of(url) if url else ''}\n")
    return ok

def main():
    args = sys.argv[1:]
    if "--json" in args:
        json_main(args)
        return
    dry = "--dry-run" in args
    if "--url" in args:
        url = args[args.index("--url") + 1]
        rec, ok, detail = scrape_and_store(url)
        print(("OK" if ok else "FAIL"), rec, detail)
        sys.exit(0 if ok else 1)
    processed = process_issues(dry=dry)
    skip = {host_of(parse_issue_url("", ""))}  # noop
    # don't re-scrape hosts we just processed
    # parse from sources last_run today... just skip all just-processed hosts
    # process_issues already scraped them
    just = set()
    data = load_sources()
    # skip hosts updated in this run via issues: those with last_run within a minute? simpler: pass nothing, refresh will re-scrape
    # To save time, skip hosts whose last_run is in the last 10 minutes
    now = dt.datetime.now()
    skip = set()
    for s in data.get("added") or []:
        try:
            t = dt.datetime.strptime(s.get("last_run") or "", "%Y-%m-%d %H:%M")
            if (now - t).total_seconds() < 600: skip.add(s["host"])
        except Exception:
            pass
    refresh_added(skip_hosts=skip)

if __name__ == "__main__":
    main()
