#!/usr/bin/env python3
"""Lebriz.com archive importer.

lebriz.com closed on 30 Mar 2023 and is kept online as a frozen archive. From the box the live site is
unreachable (HTTPS cert expired + 404, HTTP 500), so pages are read from the Internet Archive's
Wayback Machine copies of lebriz.com (public). Every fetched page is cached in lebriz_cache/pages, so
re-runs only fetch what is missing. Polite: one request at a time, ~1.5 s apart, retries with backoff.
Usage: python3 lebriz.py [--max-exh N]   (exhibitions are crawled newest-first and resumable)
"""
import re, os, sys, html, json, time, hashlib, sqlite3, urllib.request, urllib.parse
HERE = os.path.dirname(os.path.abspath(__file__)); CACHE = os.path.join(HERE, "lebriz_cache")
DB = os.path.join(HERE, "auctions.db"); UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36"
WB = "https://web.archive.org/web/"
_last = [0.0]

import socket
socket.setdefaulttimeout(60)
def net(url, timeout=60):
    for i in range(5):
        wait = 1.5 - (time.time() - _last[0])
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
        time.sleep(5 * (i + 1))
    raise RuntimeError(f"fetch failed {url}: {err}")

def cdx(prefix, name):
    f = os.path.join(CACHE, f"cdx_{name}.txt")
    if os.path.exists(f) and os.path.getsize(f) > 100: return open(f, encoding="utf8").read().splitlines()
    q = urllib.parse.urlencode({"url": prefix, "matchType": "prefix", "filter": "statuscode:200", "fl": "timestamp,original,length", "collapse": "urlkey"})
    t = net("https://web.archive.org/cdx/search/cdx?" + q, timeout=300).decode("utf8", "replace")
    if "<html" in t[:200].lower(): raise RuntimeError("cdx returned html")
    open(f, "w", encoding="utf8").write(t); return t.splitlines()

def page(ts, url):
    """Archived HTML (raw, id_) or None if it is the BrowserHawk interstitial / too small."""
    f = os.path.join(CACHE, "pages", hashlib.sha1((ts + url).encode()).hexdigest() + ".html")
    if os.path.exists(f): b = open(f, "rb").read()
    else:
        b = net(f"{WB}{ts}id_/{url}"); open(f, "wb").write(b)
    h = b.decode("utf8", "replace")
    return None if (len(b) < 6000 or "bhawkTest" in h) else h

def best(entries):
    """Order candidate snapshots: big pages first, Turkish first, newest first."""
    ok = [e for e in entries if len(e) >= 3 and e[2].isdigit() and int(e[2]) > 8000]
    return sorted(ok, key=lambda e: ("lang=TR" in e[1], e[0]), reverse=True)

def first_page(entries, tries=3):
    for e in best(entries)[:tries]:
        h = page(e[0], e[1])
        if h: return h, e
    return None, None

T = lambda s: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()
def wbimg(u, ts): return f"{WB}{ts[:4]}im_/{html.unescape(u)}" if u else ""

def auctions(db):
    """Lebriz 'Müzayede Bilgi Bankası' catalogue pages (auction_Cat.aspx). Archived copies are partial:
    usually only the first page (3 lots) of each sort order (lot no / artist / price asc / price desc)."""
    A = [l.split(" ") for l in cdx("lebriz.com/pages/auction", "auction")]
    done = {r[0] for r in db.execute("SELECT url FROM lb_fetched")}
    todo = [e for e in A if len(e) > 2 and "auction_Cat" in e[1] and e[2].isdigit() and int(e[2]) > 8000 and e[0] + e[1] not in done]
    print("auction catalogue snapshots to read:", len(todo), flush=True)
    for n, e in enumerate(todo):
        ma = re.search(r"aucID=(\d+)", e[1], re.I)
        if not ma: continue
        h = page(e[0], e[1]); aid = int(ma.group(1))
        if h:
            t = T(re.sub(r"<script.*?</script>|<style.*?</style>", "", h, flags=re.S))
            m = re.search(r"Lot No Sanatçı Fiyat (.+?) Toplam eser sayısı", t); name = m.group(1).strip() if m else None
            for m in re.finditer(r"lot no : (\d+) (.+?) ([\d,.]+) (TRL|YTL|TL|USD|EUR|GBP)\b", t):
                db.execute("INSERT OR REPLACE INTO lb_auction_lots VALUES(?,?,?,?,?,?,?)", (aid, int(m.group(1)), m.group(2).strip(), float(m.group(3).replace(",", "")), m.group(4), name, e[0]))
        db.execute("INSERT OR IGNORE INTO lb_fetched VALUES(?)", (e[0] + e[1],)); db.commit()
        if n % 25 == 0: print(f"auc [{n+1}/{len(todo)}]", flush=True)

def main():
    max_exh = int(sys.argv[sys.argv.index("--max-exh") + 1]) if "--max-exh" in sys.argv else 10**9
    db = sqlite3.connect(DB, timeout=60)
    db.executescript("""
    CREATE TABLE IF NOT EXISTS lb_artists(artist_id INTEGER PRIMARY KEY, name, years, bio, bio_source, works_total INT, auction_catalogue_works INT, url, snapshot);
    CREATE TABLE IF NOT EXISTS lb_series(artist_id INT, name, count INT, PRIMARY KEY(artist_id, name));
    CREATE TABLE IF NOT EXISTS lb_artist_exh(artist_id INT, kind, date, text, exh_id INT, PRIMARY KEY(artist_id, kind, date, text));
    CREATE TABLE IF NOT EXISTS lb_exhibitions(exh_id INTEGER PRIMARY KEY, gallery, title, date_start, date_end, works_count INT, address, city, url, snapshot);
    CREATE TABLE IF NOT EXISTS lb_exh_works(exh_id INT, code, artist, title, size, technique, image, PRIMARY KEY(exh_id, code));
    CREATE TABLE IF NOT EXISTS lb_meta(k PRIMARY KEY, v);
    CREATE TABLE IF NOT EXISTS lb_auction_lots(auc_id INT, lot_no INT, artist, price REAL, currency, auction, snapshot, PRIMARY KEY(auc_id, lot_no));
    CREATE TABLE IF NOT EXISTS lb_fetched(url PRIMARY KEY);""")
    if "--auctions-only" not in sys.argv and "--skip-auctions" not in sys.argv or "--auctions-only" in sys.argv:
        auctions(db)
        if "--auctions-only" in sys.argv: return
    # ---- artist list
    L = [l.split(" ") for l in cdx("lebriz.com/pages/artist.aspx", "artist")]
    cand = sorted([e for e in L if "listType=general" in e[1] and "artistID" not in e[1] and "filterType=-1" in e[1] and len(e) > 2 and e[2].isdigit()], key=lambda e: int(e[2]), reverse=True)
    lst = None
    for e in cand[:4]:
        lst = page(e[0], e[1])
        if lst: break
    if not lst: raise SystemExit("artist list snapshot not available")
    artists = {}
    for m in re.finditer(r'artistID=(\d+)"[^>]*>([^<]+)</a>', lst): artists[int(m.group(1))] = T(m.group(2))
    print("artists in list:", len(artists))
    by = {}
    for e in L:
        m = re.search(r"artistID=(\d+)", e[1]); s = re.search(r"section=(\d+)", e[1])
        if m and s and "periodID=5" not in e[1]:
            if re.search(r"periodID=\d", e[1]) or re.search(r"pageNo=[1-9]", e[1]) or re.search(r"exhID=[1-9]", e[1]): continue
            by.setdefault((int(m.group(1)), s.group(1)), []).append(e)
    done = {r[0] for r in db.execute("SELECT artist_id FROM lb_artists WHERE snapshot IS NOT NULL")}
    for n, (aid, name) in enumerate(sorted(artists.items())):
        if aid in done: continue
        url = f"http://www.lebriz.com/pages/artist.aspx?section=100&lang=TR&artistID={aid}"
        bio = years = None; src = None; total = auc = None; snap = None
        h, e = first_page(by.get((aid, "120"), []))
        if h:
            m = re.search(r'\((\d{4}\s*-\s*(?:\d{4})?)\s*\)', T(re.search(r'Özgeçmiş(.{0,0})', h) and h[:0] or "") or "")
            hd = re.search(re.escape(name.strip()) + r"\s*\(([^)]{4,15})\)", T(h))
            years = hd.group(1) if hd else None
            parts = [T(x) for x in re.findall(r'id="lebrizArtist_bio_dov_docPage_lblBody\d+"[^>]*>(.*?)</span>', h, re.S)]
            bio = "\n\n".join(p for p in parts if p) or None
            src = f"{WB}{e[0]}/{e[1]}"; snap = e[0]
        h, e = first_page(by.get((aid, "130"), []))
        if h:
            for m in re.finditer(r'class="rmText">([^<]{2,90}?)\s*\((\d+)\)</span>', h):
                nm, c = T(m.group(1)), int(m.group(2))
                if nm == "Bütün Katalog": total = c
                elif nm == "Müzayede Kataloglarında": auc = c
                elif not nm.startswith("Online") and not nm.startswith("Galeri"):
                    db.execute("INSERT OR REPLACE INTO lb_series VALUES(?,?,?)", (aid, nm, c))
            if not years:
                hd = re.search(re.escape(name.strip()) + r"\s*\(([^)]{4,15})\)", T(h)); years = hd.group(1) if hd else None
            snap = snap or e[0]
        h, e = first_page(by.get((aid, "140"), []))
        if h:
            for kind, key in (("online", "Online"), ("solo", "Solo"), ("group", "Group")):
                for m in re.finditer(rf'dlstExh{key}_ctl\d+_tdDate"[^>]*>(.*?)</td><td[^>]*dlstExh{key}_ctl\d+_tdExh"[^>]*>(.*?)</td>', h, re.S):
                    ex = re.search(r"exhID=(\d+)", m.group(0))
                    db.execute("INSERT OR REPLACE INTO lb_artist_exh VALUES(?,?,?,?,?)", (aid, kind, T(m.group(1)), T(m.group(2)), int(ex.group(1)) if ex and ex.group(1) != "0" else None))
            snap = snap or e[0]
        db.execute("INSERT OR REPLACE INTO lb_artists VALUES(?,?,?,?,?,?,?,?,?)", (aid, name.strip(), years, bio, src, total, auc, url, snap or None))
        db.commit(); print(f"[{n+1}/{len(artists)}] {name.strip()} bio={'y' if bio else '-'} works={total} snap={snap}", flush=True)
    # ---- exhibitions (newest id first)
    E = [l.split(" ") for l in cdx("lebriz.com/pages/exhibition.aspx", "exhibition")]
    ex = {}
    for e in E:
        m = re.search(r"exhID=(\d+)", e[1])
        if m and "pageNo" not in e[1]: ex.setdefault(int(m.group(1)), []).append(e)
    done = {r[0] for r in db.execute("SELECT exh_id FROM lb_exhibitions")}
    todo = [i for i in sorted(ex, reverse=True) if i not in done and best(ex[i])][:max_exh]
    print("exhibitions archived:", len(ex), "to fetch:", len(todo))
    for n, i in enumerate(todo):
        h, e = first_page(ex[i], tries=2)
        if not h:
            db.execute("INSERT OR REPLACE INTO lb_exhibitions(exh_id) VALUES(?)", (i,)); db.commit(); continue
        g = lambda id_: T((re.search(rf'id="{id_}"[^>]*>(.*?)</(?:a|span|td)>', h, re.S) or [None, ""])[1])
        dates = g("exh_exhHead_lblDates"); d = re.findall(r"\d{2}\.\d{2}\.\d{4}", dates)
        addr = g("exh_exhFoot_bizCard_tdAddress"); city = addr.split()[-1] if addr else None
        cnt = re.search(r"Toplam eser sayısı :(?:&nbsp)?\s*<b>(\d+)</b>", h)
        db.execute("INSERT OR REPLACE INTO lb_exhibitions VALUES(?,?,?,?,?,?,?,?,?,?)", (i, g("exh_exhHead_lgdGallery_hypLogo"), g("exh_exhHead_lblName"),
            d[0] if d else None, d[1] if len(d) > 1 else None, int(cnt.group(1)) if cnt else None, addr, city,
            f"http://www.lebriz.com/pages/exhibition.aspx?lang=TR&exhID={i}", e[0]))
        for m in re.finditer(r'<input type="image"[^>]*title="([^"]*)"[^>]*src="([^"]+)"', h):
            t = html.unescape(m.group(1)).replace("Detaylı bilgi ve büyük resim için tıklayın", "").strip()
            c = re.match(r"Eser kodu : (\S+)\s*(.*)", t)
            if not c: continue
            rest = c.group(2); sz = re.search(r"\d+(?:[.,]\d+)?\s*x\s*\d+(?:[.,]\d+)?(?:\s*x\s*\d+(?:[.,]\d+)?)?\s*cm", rest)
            before, after = (rest[:sz.start()].strip(), rest[sz.end():].strip()) if sz else (rest, "")
            db.execute("INSERT OR REPLACE INTO lb_exh_works VALUES(?,?,?,?,?,?,?)", (i, c.group(1), None, before, sz.group(0) if sz else None, after, wbimg(m.group(2), e[0])))
        db.commit()
        if n % 25 == 0: print(f"exh [{n+1}/{len(todo)}] {i} {dates}", flush=True)
    db.execute("INSERT OR REPLACE INTO lb_meta VALUES('updated', datetime('now','localtime'))"); db.commit()

if __name__ == "__main__": main()
