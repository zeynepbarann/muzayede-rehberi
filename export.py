#!/usr/bin/env python3
"""Build self-contained index.html (data embedded) from auctions.db."""
import sqlite3, json, os
HERE = os.path.dirname(os.path.abspath(__file__))
def build():
    db = sqlite3.connect(os.path.join(HERE, "auctions.db")); db.row_factory = sqlite3.Row
    lots = [dict(r) for r in db.execute("SELECT * FROM lots WHERE end_date IS NULL OR end_date > strftime('%Y-%m-%d %H:%M','now','localtime') ORDER BY end_date IS NULL, end_date, site, CAST(lot_no AS INT)")]
    for l in lots: l["images"] = json.loads(l["images"] or "[]")
    last = db.execute("SELECT max(at) FROM runs").fetchone()[0]
    runs = [dict(r) for r in db.execute("SELECT site,status,lots,detail FROM runs WHERE at=?", (last,))]
    # past lots (seen in earlier runs, not live now): latest snapshot of each, for artist value stats
    past = [dict(r) for r in db.execute("""SELECT h.site,h.lot_id,h.artist,h.title,h.description,h.start_price,h.bid_count,h.auction,h.end_date,h.url,h.image,h.at
        FROM price_history h JOIN (SELECT site,lot_id,max(at) m FROM price_history GROUP BY site,lot_id) x ON h.site=x.site AND h.lot_id=x.lot_id AND h.at=x.m
        WHERE NOT EXISTS (SELECT 1 FROM lots l WHERE l.site=h.site AND l.lot_id=h.lot_id)""")]
    hist = {}
    for r in db.execute("SELECT site||'|'||lot_id k, at, start_price, bid_count FROM price_history ORDER BY at"):
        hist.setdefault(r[0], []).append([r[1], r[2], r[3]])
    for l in lots: l["history"] = hist.get(l["site"] + "|" + l["lot_id"], [])
    tpl = open(os.path.join(HERE, "template.html"), encoding="utf8").read()
    data = json.dumps({"lots": lots, "past": past, "runs": runs, "updated": last}, ensure_ascii=False).replace("</", "<\\/")
    return tpl.replace("/*DATA*/null", data)
if __name__ == "__main__":
    open(os.path.join(HERE, "index.html"), "w", encoding="utf8").write(build()); print("wrote index.html")
