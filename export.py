#!/usr/bin/env python3
"""Build the site from auctions.db:
  index.html       small HTML shell (template.html + a tiny META block)
  data/lots.json   live lots (canonical artist names)
  data/past.json   latest snapshot of lots no longer live
  data/artists.json  canonical artists + variants
  data/sources.json  user-added sources and their last-run status
Lebriz files (data/lebriz_*.json) are written by lebriz_export.py."""
import sqlite3, json, os, artists
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "data")
KEEP = ["site","lot_id","lot_no","artist","description","category","start_price","estimate","current_bid","bid_count","auction","auction_type","end_date","images","url"]
OPTIONAL = ["title","artist_raw","lb_id","history"]
def dump(name, obj):
    os.makedirs(OUT, exist_ok=True); tmp = os.path.join(OUT, name + ".tmp")
    with open(tmp, "w", encoding="utf8") as f: json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, os.path.join(OUT, name))
def build(write_data=True):
    db = sqlite3.connect(os.path.join(HERE, "auctions.db")); db.row_factory = sqlite3.Row
    last = db.execute("SELECT max(at) FROM runs").fetchone()[0]
    runs = [dict(r) for r in db.execute("SELECT site,status,lots,detail FROM runs WHERE at=?", (last,))]
    count = None
    artist_stats = None
    sources = {"added": []}
    sp = os.path.join(HERE, "sources.json")
    if os.path.exists(sp):
        sources = json.load(open(sp, encoding="utf8"))
    if write_data:
        lots = []
        for r in db.execute("SELECT * FROM lots WHERE end_date IS NULL OR end_date > strftime('%Y-%m-%d %H:%M','now','localtime') ORDER BY end_date IS NULL, end_date, site, CAST(lot_no AS INT)"):
            l = {k: r[k] for k in KEEP}; l["images"] = json.loads(l["images"] or "[]")
            if (r["title"] or "") not in ("", (r["artist"] or "") + " - " + (r["description"] or "")): l["title"] = r["title"]
            lots.append(l)
        hist = {}
        for r in db.execute("SELECT site||'|'||lot_id k, at, start_price, bid_count FROM price_history ORDER BY at"):
            hist.setdefault(r[0], []).append([r[1], r[2], r[3]])
        for l in lots:
            h = hist.get(l["site"] + "|" + l["lot_id"])
            if h: l["history"] = h
        past = [dict(r) for r in db.execute("""SELECT h.site,h.lot_id,h.artist,h.description,h.start_price,h.auction,h.end_date,h.url,h.image
            FROM price_history h JOIN (SELECT site,lot_id,max(at) m FROM price_history GROUP BY site,lot_id) x ON h.site=x.site AND h.lot_id=x.lot_id AND h.at=x.m
            WHERE NOT EXISTS (SELECT 1 FROM lots l WHERE l.site=h.site AND l.lot_id=h.lot_id)""")]
        lb_artists = []
        lip = os.path.join(OUT, "lebriz_index.json")
        if os.path.exists(lip):
            lb_artists = json.load(open(lip, encoding="utf8")).get("artists") or []
        artist_stats, _ = artists.apply_to_lots(lots, past, lb_artists)
        dump("lots.json", {"updated": last, "lots": lots})
        dump("past.json", past)
        dump("artists.json", artist_stats)
        dump("sources.json", sources)
        count = len(lots)
        print(f"artists: {artist_stats['raw']} raw → {artist_stats['canon']} canonical ({artist_stats['merged']} merged)")
    meta = {"updated": last, "runs": runs, "v": (last or "").replace(" ", "T"), "count": count,
            "artists": {"raw": (artist_stats or {}).get("raw"), "canon": (artist_stats or {}).get("canon")},
            "sources": sources.get("added") or []}
    tpl = open(os.path.join(HERE, "template.html"), encoding="utf8").read()
    return tpl.replace("/*META*/null", json.dumps(meta, ensure_ascii=False).replace("</", "<\\/"))
if __name__ == "__main__":
    open(os.path.join(HERE, "index.html"), "w", encoding="utf8").write(build()); print("wrote index.html + data/{lots,past,artists,sources}.json")
