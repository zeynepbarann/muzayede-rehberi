#!/usr/bin/env python3
"""Scrape ongoing auction lots into auctions.db. Public pages only."""
import re, html, json, sqlite3, time, sys, datetime as dt, urllib.request, os
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36"
HERE = os.path.dirname(os.path.abspath(__file__)); DB = os.path.join(HERE, "auctions.db")
MUZAYEDEAPP = ["www.nefsmuzayede.com","www.dedemuzayede.com","www.anatoliamuzayede.com","www.kassanat.com",
               "www.turkartproject.com","www.uxmuzayede.com","www.ranasartgallery.com","www.galeriberlin.com",
               "www.kalamismuzayede.com","www.aysilmuzayede.com","www.nisartgallery.com"]

def get(url, data=None, tries=3):
    for i in range(tries):
        try:
            h = {"User-Agent": UA, "Accept": "text/html,application/json", "Accept-Language": "tr-TR,tr;q=0.9"}
            if data is not None: h["Content-Type"] = "application/json"; data = json.dumps(data).encode() if not isinstance(data, bytes) else data
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h), timeout=40) as r:
                return r.read().decode("utf-8", "ignore")
        except Exception as e:
            err = e; time.sleep(2 + i * 3)
    raise err

def txt(s): return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()
def num(s):
    s = (s or "").replace(".", "").replace(",", ".").strip()
    try: v = float(s); return v if v > 0 else None
    except: return None

def scrape_muzayedeapp(host):
    base = "https://" + host; site = host.replace("www.", "")
    home = get(base + "/")
    ids = {}
    for m in re.finditer(r'href="(?:https?://(?:www\.)?[^/"]+)?/muzayede/(\d+)/([^"/?#]+)"', home):
        ids[m.group(1)] = m.group(2)
    lots, auctions = [], []
    for aid, slug in ids.items():
        url = f"{base}/muzayede/{aid}/{slug}"
        page = get(url)
        ms = re.search(r'muzayedeappRemaining\(\{\s*auctionId: parseInt\("%s".*?milliseconds: parseInt\("(-?\d+)' % aid, page, re.S)
        remain = int(ms.group(1)) if ms else 0
        if remain <= 0: auctions.append((site, aid, "ended/not live", 0)); continue
        end = (dt.datetime.now() + dt.timedelta(milliseconds=remain)).strftime("%Y-%m-%d %H:%M")
        m = re.search(r'auctionName: "([^"]*)"', page); aname = html.unescape(m.group(1)) if m else slug
        seen, n, cnt = set(), 1, 0
        while page:
            new = 0
            for blk in re.split(r'(?=<div class="item" id="product-item-)', page)[1:]:
                g = lambda a: (re.search(a + r'="([^"]*)"', blk) or [None, ""])[1]
                pid = g("data-id")
                if not pid or pid in seen: continue
                seen.add(pid); new += 1
                lc = blk[blk.find('class="lot-content"'):]
                href = (re.search(r'href="(/urun/[^"]+)"', lc) or [None, ""])[1]
                artist = txt((re.search(r'<p class="lot-title">(.*?)</p>', lc, re.S) or [None, ""])[1])
                ps = re.findall(r'<a href="/urun/[^"]+">\s*<p>(.*?)</p>', lc, re.S)
                desc = txt(ps[0]) if ps else ""
                cat = txt((re.search(r'class="tag-name">(.*?)<', lc) or [None, ""])[1])
                imgs = list(dict.fromkeys(re.findall(r'p-image-l" data-src="([^"]+)"', blk)))
                if not imgs: imgs = list(dict.fromkeys(re.findall(r'data-src="([^"]+)"', blk)))
                lots.append(dict(site=site, lot_id=pid, lot_no=g("data-lotno"), title=(artist + " - " + desc).strip(" -"),
                    artist=artist, description=desc, category=cat, start_price=num(g("data-price")),
                    estimate=num(g("data-estimated-price")), current_bid=num(g("data-offer-price")),
                    bid_count=int(g("data-offer-count") or 0), currency="TL", auction=aname, auction_type="auction",
                    end_date=end, images=json.dumps(imgs), url=base + href))
            cnt += new
            if new == 0 or f"/sayfa/{n+1}" not in page: break
            n += 1; time.sleep(0.7); page = get(f"{url}/sayfa/{n}")
        auctions.append((site, aid, aname, cnt))
    return lots, auctions

def scrape_artvela():
    r = json.loads(get("https://ws.artvela.com/api/tip9Icerik", {"Id": 32}))
    lots, auctions = [], []
    for a in r.get("data") or []:
        end = dt.datetime.fromisoformat(a["bitisi"])
        auctions.append(("artvela.com", a["Id"], a["tanim"] + ("" if end > dt.datetime.now() else " (ended " + a["bitis"] + ")"), 0))
        # Lot listing for an active Artvela auction is loaded by the SPA; not reachable while none is active.
    return lots, auctions

def scrape_sanatsal():
    page = get("https://sanatsalmuzayede.com/eserler"); lots = []
    for art in re.findall(r'<article class="group.*?</article>', page, re.S):
        href = (re.search(r'href="(/eser/[^"]+)"', art) or [None, ""])[1]
        if not href: continue
        artist = txt((re.search(r'<h3[^>]*>(.*?)</h3>', art, re.S) or [None, ""])[1])
        desc = txt((re.search(r'<p class="text-sm text-muted-foreground mt-2">(.*?)</p>', art, re.S) or [None, ""])[1])
        img = (re.search(r'<img src="([^"]+)"', art) or [None, ""])[1]
        price = re.search(r'Hemen Al</p><p[^>]*>([\d.]+)', art)
        lots.append(dict(site="sanatsalmuzayede.com", lot_id=href.rsplit("--", 1)[-1], lot_no="", title=(artist + " - " + desc).strip(" -"),
            artist=artist, description=desc, category="", start_price=num(price.group(1)) if price else None, estimate=None,
            current_bid=None, bid_count=0, currency="TL", auction="Eserler (Hemen Al / teklif)", auction_type="buy-now",
            end_date=None, images=json.dumps(["https://sanatsalmuzayede.com" + html.unescape(img)] if img else []),
            url="https://sanatsalmuzayede.com" + href))
    return lots, [("sanatsalmuzayede.com", "eserler", "Eserler (buy-now catalogue)", len(lots))]

ARTAM = "https://artam.com"; ARTAM_IMG = "https://img.artam.com/storage"
def scrape_artam():
    """Artam online auctions: the page loads lots from a JSON API (24 per page)."""
    r = json.loads(get(ARTAM + "/muzayede/get-auctions?current=true"))
    lots, aucs, now = [], [], dt.datetime.now()
    for a in r.get("auctions") or []:
        end = dt.datetime.strptime((a.get("finishedAt") or "")[:16], "%d.%m.%Y %H:%M")
        title = f"Artam {a.get('saleNo')}. Müzayede – {(a.get('name') or '').strip().title().replace(' Ve ', ' ve ')}"
        if end <= now or a.get("isFinished"):
            aucs.append(("artam.com", a["id"], title + " (bitti)", 0)); continue
        base = ARTAM + (a.get("url") or a.get("detailPageSlug") or "/muzayede/" + a.get("slug", ""))
        # The API ignores "page" but returns the first <count> lots, so ask for all of them at once.
        seen, cnt, want, prods = set(), 0, 400, []
        while True:
            prods = json.loads(get(f"{ARTAM}/api/v1/auction/online-products/get-all?auction_id={a['id']}&page=1&count={want}")).get("products") or []
            if len(prods) < want or want >= 6400: break
            want *= 2; time.sleep(0.6)
        if True:
            for p in [p for p in prods if p.get("id") not in seen]:
                seen.add(p["id"]); cnt += 1
                imgs = []
                for im in p.get("images") or []:
                    f = ((im.get("conversions") or {}).get("large") or {}).get("filename") or im.get("filename")
                    if f: imgs.append(ARTAM_IMG + f)
                name, short = (p.get("fullName") or p.get("name") or "").strip(), txt(p.get("short_description") or "")
                artist = txt(p.get("artistName") or "")
                bids = int(p.get("offersCount") or 0)
                try: opening = float(p.get("opening_price") or 0) or None
                except ValueError: opening = None
                cur = float(p["auction_price"]) if bids and p.get("auction_price") else None
                fin = (p.get("finishTime") or "")[:16].replace("T", " ") or end.strftime("%Y-%m-%d %H:%M")
                lots.append(dict(site="artam.com", lot_id=str(p["id"]), lot_no=str(p.get("lotno") or ""),
                    title=(artist + " - " + name).strip(" -"), artist=artist, description=", ".join(x for x in (name, short) if x),
                    category="", start_price=opening, estimate=None, current_bid=cur, bid_count=bids, currency="TL",
                    auction=title, auction_type="auction", end_date=fin, images=json.dumps(imgs[:8]),
                    url=base + (p.get("detailPageUrl") or "")))
        aucs.append(("artam.com", a["id"], title, cnt))
    return lots, aucs

ART_KW = r"sanat|resim|tablo|çağdaş|ÇAĞDAŞ|cagdas|modern|\bart\b|tuval|plastik|hat\b|HAT\b|minyatür"
def page_description(page):
    """Description of a MüzayedeApp work page: og/meta description, else the explanation block."""
    for pat in (r'<meta[^>]+property="og:description"[^>]+content="([^"]*)"', r'<meta[^>]+content="([^"]*)"[^>]+property="og:description"',
                r'<meta[^>]+name="description"[^>]+content="([^"]*)"', r'class="lot-explanation"[^>]*>(.*?)</',
                r'class="product-description"[^>]*>(.*?)</div>', r'class="description"[^>]*>(.*?)</div>'):
        m = re.search(pat, page, re.S | re.I)
        if m:
            d = txt(m.group(1))
            if len(d) > 4 and "müzayedeapp" not in d.lower(): return d
    return ""

def fill_descriptions(lots, limit=300):
    """Some houses (e.g. THE_ONLINE) list only the artist name; read size/technique from each work's page."""
    n = 0
    for l in lots:
        if l.get("description") or n >= limit or not l.get("url"): continue
        n += 1
        try:
            d = page_description(get(l["url"], tries=2))
            if d: l["description"] = d.rstrip(".")
        except Exception:
            pass
        time.sleep(0.5)

def scrape_mapp_portal(skip_ids):
    """Art auctions (categories Resim/Hat, or Karma with art keywords) listed on muzayedeapp.com."""
    base = "https://www.muzayedeapp.com"; h = get(base + "/")
    h = h[h.find('class="auction-list"'):]
    G = lambda p, b: (re.search(p, b, re.S) or [None, ""])[1]
    out = {}
    for blk in h.split('<div class="item hd">')[1:]:
        m = re.search(r'data-category-id="(\d+)" data-id="(\d+)"', blk)
        if not m: continue
        cat, aid = m.groups(); name = html.unescape(G(r'class="ellipsis">([^<]*)', blk))
        if not (cat in ("7", "17") or (cat == "8" and re.search(ART_KW, name, re.I))): continue
        if int(G(r'data-end="(\d+)"', blk) or 0) / 1000 < time.time(): continue
        house = html.unescape(G(r'auction-house-name[^>]*>([^<]*)', blk) or G(r'title="([^"]*)"', blk))
        out[aid] = (house, name, base + G(r'href="(/muzayede/[^"]+)"', blk))
    res = {}
    for aid, (house, aname, url) in out.items():
        site = "muzayedeapp: " + house; lots = []; seen = set(); n = 1; page = get(url)
        endms = int(G(r'class="item remaining[^"]*" data-end="(\d+)"', page) or 0)
        end = dt.datetime.fromtimestamp(endms / 1000).strftime("%Y-%m-%d %H:%M") if endms else None
        while True:
            new = 0
            for blk in re.split(r'(?=<div class="item"\s+data-kkp=")', page)[1:]:
                pid = G(r'data-kkp="(\d+)"', blk)
                if not pid or pid in seen: continue
                seen.add(pid); new += 1
                if pid in skip_ids: continue
                a = re.search(r'<div class="content">\s*<a href="([^"]+)">(.*?)<p\s+class="lot-explanation">(.*?)</p>', blk, re.S)
                if not a: continue
                artist, desc = txt(a.group(2)), txt(a.group(3)).rstrip(".")
                lotno = G(r'Lot No: (\d+)', blk); cat_t = txt(G(r'</strong>([^<]*)</span>', blk))
                imgs = list(dict.fromkeys(re.findall(r'data-full="([^"]+)"', blk)))
                cur = num(re.sub(r"[^\d.,]", "", G(r'class="current-price"\s*>(.*?)</strong>', blk)))
                opn = num(re.sub(r"[^\d.,]", "", G(r'Açılış</strong>\s*<p>(.*?)</p>', html.unescape(blk))))
                bids = int(G(r'<strong>Peyler</strong>\s*<p>(\d+)', blk) or 0)
                lots.append(dict(site=site, lot_id=pid, lot_no=lotno, title=(artist + " - " + desc).strip(" -"), artist=artist,
                    description=desc, category=cat_t, start_price=opn, estimate=None, current_bid=cur if bids else None,
                    bid_count=bids, currency="TL", auction=aname, auction_type="auction", end_date=end,
                    images=json.dumps(imgs), url=base + a.group(1)))
            if new == 0: break
            n += 1; time.sleep(0.7); page = get(f"{url}?pageNumber={n}")
        fill_descriptions(lots)
        res.setdefault(site, ([], []))
        res[site][0].extend(lots); res[site][1].append((site, aid, aname, len(lots)))
    return res

def main():
    db = sqlite3.connect(DB)
    db.executescript("""DROP TABLE IF EXISTS lots_fts;
    CREATE TABLE IF NOT EXISTS lots(site,lot_id,lot_no,title,artist,description,category,start_price REAL,estimate REAL,current_bid REAL,
      bid_count INT,currency,auction,auction_type,end_date,images,url,scraped_at, PRIMARY KEY(site,lot_id));
    CREATE VIRTUAL TABLE lots_fts USING fts5(title,artist,description,auction,site, content='lots');
    CREATE TABLE IF NOT EXISTS runs(at,site,status,lots,detail);
    CREATE TABLE IF NOT EXISTS price_history(at,site,lot_id,artist,title,description,start_price REAL,estimate REAL,current_bid REAL,bid_count INT,auction,end_date,url,image, PRIMARY KEY(at,site,lot_id));""")
    now = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    jobs = [(h.replace("www.", ""), lambda h=h: scrape_muzayedeapp(h)) for h in MUZAYEDEAPP]
    jobs += [("artvela.com", scrape_artvela), ("sanatsalmuzayede.com", scrape_sanatsal), ("artam.com", scrape_artam)]
    for site, fn in jobs:
        try:
            lots, aucs = fn()
            # success: replace this site's lots (also clears ended auctions). On error we never get here,
            # so the previous lots for the site are kept.
            db.execute("DELETE FROM lots WHERE site=?", (site,))
            for l in lots:
                l["scraped_at"] = now
                db.execute("INSERT OR REPLACE INTO price_history VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (now,l["site"],l["lot_id"],l["artist"],l["title"],l["description"],l["start_price"],l["estimate"],l["current_bid"],l["bid_count"],l["auction"],l["end_date"],l["url"],(json.loads(l["images"]) or [None])[0]))
                db.execute(f"INSERT OR REPLACE INTO lots({','.join(l)}) VALUES({','.join('?'*len(l))})", list(l.values()))
            detail = "; ".join(f"{a[2]} [{a[3]} lots]" for a in aucs) or "no auction links on homepage"
            db.execute("INSERT INTO runs VALUES(?,?,?,?,?)", (now, site, "ok", len(lots), detail))
            print(f"{site:28} OK   {len(lots):5} lots | {detail}")
        except Exception as e:
            db.execute("INSERT INTO runs VALUES(?,?,?,?,?)", (now, site, "fail", 0, str(e)))
            kept = db.execute("SELECT count(*) FROM lots WHERE site=?", (site,)).fetchone()[0]
            print(f"{site:28} FAIL {e} (kept {kept} previous lots)")
        db.commit()
    try:
        skip = {r[0] for r in db.execute("SELECT lot_id FROM lots WHERE site NOT LIKE 'muzayedeapp:%'")}
        portal = scrape_mapp_portal(skip)
        db.execute("DELETE FROM lots WHERE site LIKE 'muzayedeapp:%'")
        for site, (lots, aucs) in portal.items():
            for l in lots:
                l["scraped_at"] = now
                db.execute("INSERT OR REPLACE INTO price_history VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (now,l["site"],l["lot_id"],l["artist"],l["title"],l["description"],l["start_price"],l["estimate"],l["current_bid"],l["bid_count"],l["auction"],l["end_date"],l["url"],(json.loads(l["images"]) or [None])[0]))
                db.execute(f"INSERT OR REPLACE INTO lots({','.join(l)}) VALUES({','.join('?'*len(l))})", list(l.values()))
            detail = "; ".join(f"{a[2]} [{a[3]} lots]" for a in aucs)
            db.execute("INSERT INTO runs VALUES(?,?,?,?,?)", (now, site, "ok", len(lots), detail))
            print(f"{site:28} OK   {len(lots):5} lots | {detail}")
    except Exception as e:
        db.execute("INSERT INTO runs VALUES(?,?,?,?,?)", (now, "muzayedeapp.com", "fail", 0, str(e)))
        print(f"muzayedeapp.com portal FAIL {e} (kept previous portal lots)")
    db.commit()
    db.execute("INSERT INTO lots_fts(lots_fts) VALUES('rebuild')"); db.commit()

if __name__ == "__main__": main()
