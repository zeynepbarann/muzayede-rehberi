#!/usr/bin/env python3
"""Collect finished auctions of MüzayedeApp-based houses into data/past_archive_mapp.json.

These sites refuse GitHub's servers, so this runs from refresh.sh on the machine that does the
daily scan. It is incremental and time-boxed: every run adds auctions it has not seen yet
(newest first) until --minutes is used up, so the first days fill the archive and later runs
only add the auctions that ended since.

For each house it looks for its archive of past auctions (links named "Geçmiş", "Arşiv",
"Sonuçlanan", "Tamamlanan" … and a few usual addresses), collects /muzayede/<id>/<slug> links,
then reads every finished auction with the same lot reader as the daily scan. What it found is
written to data/history_log.json so the discovery can be checked and tuned.

Usage: python3 history_mapp.py [--since 2024-01-01] [--minutes 40] [--host www.nefsmuzayede.com]
"""
import os, re, sys, json, time, datetime as dt
from urllib.parse import urljoin, urlparse
import scrape

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "past_archive_mapp.json")
LOG = os.path.join(HERE, "data", "history_log.json")
ARCHIVE_PATHS = ["/gecmis-muzayedeler", "/gecmis-muzayede", "/muzayedeler/gecmis", "/sonuclanan-muzayedeler",
                 "/tamamlanan-muzayedeler", "/muzayede-arsivi", "/arsiv", "/muzayedeler"]
KW = re.compile(r"geçmiş|gecmis|arşiv|arsiv|sonuçlanan|sonuclanan|tamamlanan|biten|past", re.I)
AUC = re.compile(r'href="(?:https?://[^/"]+)?/muzayede/(\d+)/([^"/?#]+)"')


def houses():
    hs = list(scrape.MUZAYEDEAPP)
    try:
        for s in json.load(open(os.path.join(HERE, "sources.json"), encoding="utf8")).get("added") or []:
            if (s.get("method") or "").startswith("muzayedeapp") and s.get("kind") != "product":
                h = urlparse(s["url"]).netloc
                h = h if h.startswith("www.") else "www." + h
                if h not in hs and "muzayedeapp.com" not in h: hs.append(h)
    except Exception:
        pass
    return hs


def links(page, base):
    return [(urljoin(base, h), scrape.txt(t)) for h, t in re.findall(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>', page, re.S)]


def discover(host, log):
    """Auction ids/slugs a house links to from its archive pages (and home page)."""
    base = "https://" + host
    found, tried = {}, []
    home = scrape.get(base + "/", tries=2)
    found.update({a: s for a, s in AUC.findall(home)})
    cands = [base + p for p in ARCHIVE_PATHS]
    cands += [u for u, t in links(home, base) if urlparse(u).netloc.endswith(host.replace("www.", "")) and KW.search(t + " " + u)]
    for u in list(dict.fromkeys(cands))[:16]:
        try:
            page = scrape.get(u, tries=1)
        except Exception as e:
            tried.append([u, str(e)[:60]]); continue
        ids = dict(AUC.findall(page)); tried.append([u, len(ids)])
        if not ids: continue
        found.update(ids)
        for n in range(2, 40):                      # follow the archive's own paging
            nxt = [x for x, _ in links(page, u) if re.search(rf"([?&](page|sayfa|p)={n}\b|/sayfa/{n}\b)", x)]
            if not nxt: break
            try: page = scrape.get(nxt[0], tries=1)
            except Exception: break
            new = dict(AUC.findall(page))
            if not set(new) - set(found): break
            found.update(new); time.sleep(0.6)
        time.sleep(0.6)
    log["tried"] = tried
    return found


def read_auction(host, aid, slug, since):
    base = "https://" + host; site = host.replace("www.", ""); url = f"{base}/muzayede/{aid}/{slug}"
    page = scrape.get(url, tries=2)
    ms = scrape.mapp_remaining_ms(page, aid)
    if ms is not None and ms > 0: return "live", []
    end = dt.datetime.now() + dt.timedelta(milliseconds=ms) if ms is not None else None
    if end and end < since: return "old", []
    m = re.search(r'auctionName: "([^"]*)"', page)
    aname = scrape.html.unescape(m.group(1)) if m else slug.replace("-", " ").title()
    lots = scrape.mapp_auction_lots(page, url, site, base, aname, end.strftime("%Y-%m-%d %H:%M") if end else None)
    out = []
    for l in lots:
        imgs = json.loads(l["images"] or "[]")
        out.append({"site": site, "lot_id": l["lot_id"], "aid": aid, "artist": l["artist"], "description": l["description"],
                    "start_price": l["start_price"], "estimate_min": l["estimate"],
                    "last_bid": l["current_bid"] if l["bid_count"] else None, "bid_count": l["bid_count"],
                    "auction": aname, "end_date": l["end_date"], "url": l["url"], "image": imgs[0] if imgs else None})
    return "ok", out


def main():
    a = sys.argv[1:]
    since = dt.datetime.strptime(a[a.index("--since") + 1], "%Y-%m-%d") if "--since" in a else dt.datetime(2024, 1, 1)
    budget = time.time() + 60 * float(a[a.index("--minutes") + 1] if "--minutes" in a else 40)
    only = a[a.index("--host") + 1] if "--host" in a else None
    archive = json.load(open(OUT, encoding="utf8")) if os.path.exists(OUT) else []
    done = {(x["site"], str(x.get("aid"))) for x in archive}
    skipped = set(tuple(x) for x in (json.load(open(LOG, encoding="utf8")).get("skip") or [])) if os.path.exists(LOG) else set()
    log = {"run": dt.datetime.now().strftime("%Y-%m-%d %H:%M"), "since": since.strftime("%Y-%m-%d"), "houses": {}, "skip": sorted(skipped)}
    added = 0
    for host in houses():
        if only and host != only: continue
        site = host.replace("www.", ""); hl = log["houses"][site] = {"auctions_found": 0, "read": 0, "lots": 0}
        if time.time() > budget: hl["note"] = "time budget used; continues next run"; continue
        try:
            found = discover(host, hl)
        except Exception as e:
            hl["error"] = str(e)[:120]; continue
        hl["auctions_found"] = len(found)
        for aid, slug in sorted(found.items(), key=lambda x: -int(x[0])):          # newest first
            if (site, aid) in done or (site, aid) in skipped: continue
            if time.time() > budget: hl["note"] = "time budget used; continues next run"; break
            try:
                state, recs = read_auction(host, aid, slug, since)
            except Exception as e:
                hl.setdefault("errors", []).append([aid, str(e)[:80]]); continue
            if state in ("old", "live"):
                if state == "old": skipped.add((site, aid))
                continue
            archive += recs; done.add((site, aid)); added += len(recs)
            hl["read"] += 1; hl["lots"] += len(recs)
            time.sleep(1.0)
    log["skip"] = sorted([list(x) for x in skipped])
    log["added"] = added; log["total"] = len(archive)
    archive.sort(key=lambda x: x.get("end_date") or "", reverse=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    tmp = OUT + ".tmp"; json.dump(archive, open(tmp, "w", encoding="utf8"), ensure_ascii=False, separators=(",", ":")); os.replace(tmp, OUT)
    json.dump(log, open(LOG, "w", encoding="utf8"), ensure_ascii=False, indent=1)
    print(f"history_mapp: +{added} works, archive {len(archive)}")


if __name__ == "__main__":
    main()
