#!/usr/bin/env python3
"""Rebuild auctions.db from the published data files, for a machine that has never run the daily scan (the cloud job's first run).

export.py derives data/past.json from the price_history table, so starting the scan with an empty database would publish an
empty archive. This puts back what the data files already know: live lots (with their daily price history) from data/lots.json
and every finished lot from data/past.json. It does nothing if auctions.db already exists.

  python3 seed_db.py            # create auctions.db if missing
"""
import json, os, sqlite3, sys
HERE = os.path.dirname(os.path.abspath(__file__)); DB = os.path.join(HERE, "auctions.db")
LOT = ["site", "lot_id", "lot_no", "title", "artist", "description", "category", "start_price", "estimate", "current_bid", "bid_count",
       "currency", "auction", "auction_type", "end_date", "images", "url", "scraped_at"]


def load(name, default):
    p = os.path.join(HERE, "data", name)
    if not os.path.exists(p):
        return default
    with open(p, encoding="utf8") as f:
        return json.load(f)


def seed():
    if os.path.exists(DB):
        print("auctions.db exists; nothing to seed"); return False
    d = load("lots.json", {"lots": []}); past = load("past.json", []); now = d.get("updated") or "2026-01-01 00:00"
    db = sqlite3.connect(DB)
    db.executescript("""CREATE TABLE IF NOT EXISTS lots(site,lot_id,lot_no,title,artist,description,category,start_price REAL,estimate REAL,current_bid REAL,
      bid_count INT,currency,auction,auction_type,end_date,images,url,scraped_at, PRIMARY KEY(site,lot_id));
    CREATE TABLE IF NOT EXISTS runs(at,site,status,lots,detail);
    CREATE TABLE IF NOT EXISTS price_history(at,site,lot_id,artist,title,description,start_price REAL,estimate REAL,current_bid REAL,bid_count INT,auction,end_date,url,image, PRIMARY KEY(at,site,lot_id));""")
    ph = "INSERT OR REPLACE INTO price_history VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
    for l in d.get("lots", []):
        artist = l.get("artist_raw") or l.get("artist")   # the published name is the merged spelling; keep the house's own where known
        title = l.get("title") or " - ".join(x for x in (artist, l.get("description")) if x)
        row = dict(l, artist=artist, title=title, currency="TRY", images=json.dumps(l.get("images") or [], ensure_ascii=False), scraped_at=now)
        db.execute("INSERT OR REPLACE INTO lots VALUES(%s)" % ",".join("?" * len(LOT)), [row.get(k) for k in LOT])
        img = (l.get("images") or [None])[0]
        for at, price, bids in (l.get("history") or [[now, l.get("start_price"), l.get("bid_count")]]):
            db.execute(ph, (at, l["site"], l["lot_id"], artist, title, l.get("description"), price, l.get("estimate"), l.get("current_bid"), bids,
                            l.get("auction"), l.get("end_date"), l.get("url"), img))
    for x in past:
        db.execute(ph, (x.get("end_date") or now, x["site"], x["lot_id"], x.get("artist"), None, x.get("description"), x.get("start_price"), None, None, 0,
                        x.get("auction"), x.get("end_date"), x.get("url"), x.get("image")))
    db.execute("INSERT INTO runs VALUES(?,?,?,?,?)", (now, "seed", "ok", len(d.get("lots", [])), "database rebuilt from data/lots.json and data/past.json"))
    db.commit(); db.close()
    print("seeded auctions.db: %d live lots, %d finished lots" % (len(d.get("lots", [])), len(past))); return True


if __name__ == "__main__":
    seed(); sys.exit(0)
