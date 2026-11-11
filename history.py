#!/usr/bin/env python3
"""Collect finished auctions further back in time into data/past_archive.json.

data/past.json only holds works the daily scan saw while they were live (since it started).
This adds older finished auctions from houses whose archives are reachable:
  - Artam: every finished online auction since --since (default 2024-01-01), with
    description, size, image and estimate (Artam does not show hammer prices publicly).
The site loads past_archive.json next to past.json. Usage:
  python3 history.py [--since 2024-01-01] [--summary out.md]
"""
import os, sys, json, time, datetime as dt
import scrape
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "data", "past_archive.json")

def num(x):
    try: v = float(x or 0); return v if v > 0 else None
    except (TypeError, ValueError): return None

def artam(since):
    out, aucs, page = [], [], 1
    while page < 200:
        r = json.loads(scrape.get(f"{scrape.ARTAM}/muzayede/get-auctions?page={page}"))
        A = r.get("auctions") or []
        if not A: break
        stop = False
        for a in A:
            try: end = dt.datetime.strptime((a.get("finishedAt") or "")[:16], "%d.%m.%Y %H:%M")
            except ValueError: continue
            if not a.get("isFinished") or end > dt.datetime.now(): continue
            if end < since: stop = True; continue
            title = f"Artam {a.get('saleNo')}. Müzayede – {(a.get('name') or '').strip().title().replace(' Ve ', ' ve ')}"
            base = scrape.ARTAM + (a.get("url") or "/muzayede/" + a.get("slug", ""))
            want, prods = 400, []
            while True:
                prods = json.loads(scrape.get(f"{scrape.ARTAM}/api/v1/auction/online-products/get-all?auction_id={a['id']}&page=1&count={want}")).get("products") or []
                if len(prods) < want or want >= 6400: break
                want *= 2
            for p in prods:
                im = (p.get("images") or [{}])[0]
                f = ((im.get("conversions") or {}).get("large") or {}).get("filename") or im.get("filename")
                name, short = (p.get("fullName") or p.get("name") or "").strip(), scrape.txt(p.get("short_description") or "")
                fin = (p.get("finishTime") or "")[:16].replace("T", " ") or end.strftime("%Y-%m-%d %H:%M")
                out.append({"site": "artam.com", "lot_id": str(p["id"]), "artist": scrape.txt(p.get("artistName") or ""),
                    "description": ", ".join(x for x in (name, short) if x), "start_price": num(p.get("opening_price")),
                    "estimate_min": num(p.get("estimatedMin")), "estimate_max": num(p.get("estimatedMax")),
                    "auction": title, "end_date": fin, "url": base + (p.get("detailPageUrl") or ""),
                    "image": (scrape.ARTAM_IMG + f) if f else None})
            aucs.append(f"{title} ({end:%d.%m.%Y}): {len(prods)} eser")
            print(aucs[-1], flush=True); time.sleep(0.8)
        if stop: break
        page += 1; time.sleep(0.5)
    return out, aucs

def main():
    a = sys.argv[1:]
    since = dt.datetime.strptime(a[a.index("--since") + 1], "%Y-%m-%d") if "--since" in a else dt.datetime(2024, 1, 1)
    summary = a[a.index("--summary") + 1] if "--summary" in a else None
    old = []
    if os.path.exists(OUT): old = json.load(open(OUT, encoding="utf8"))
    lines = []
    try:
        new, aucs = artam(since); lines += [f"- {x}" for x in aucs]
    except Exception as e:
        new = []; lines.append(f"- Artam: hata — {e}")
    keys = {(x["site"], x["lot_id"]) for x in new}
    merged = [x for x in old if (x["site"], x["lot_id"]) not in keys] + new
    merged.sort(key=lambda x: x.get("end_date") or "", reverse=True)
    if new:
        tmp = OUT + ".tmp"; json.dump(merged, open(tmp, "w", encoding="utf8"), ensure_ascii=False, separators=(",", ":")); os.replace(tmp, OUT)
    body = f"Geçmiş müzayedeler: {len(new)} eser eklendi/güncellendi (arşivde toplam {len(merged)}).\n\n" + "\n".join(lines)
    print(body)
    if summary: open(summary, "w", encoding="utf8").write(body)
    o = os.environ.get("GITHUB_OUTPUT")
    if o:
        with open(o, "a") as f: f.write(f"count={len(new)}\n")

if __name__ == "__main__": main()
