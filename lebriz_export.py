#!/usr/bin/env python3
"""Write data/lebriz_index.json and data/lebriz_artists.json from lb_* tables (loaded lazily by the page)."""
import sqlite3, json, os, re, collections
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "data"); os.makedirs(OUT, exist_ok=True)
def build():
    db = sqlite3.connect(os.path.join(HERE, "auctions.db")); db.row_factory = sqlite3.Row
    try: arts = [dict(r) for r in db.execute("SELECT * FROM lb_artists ORDER BY name")]
    except sqlite3.OperationalError: return None
    exhs = [dict(r) for r in db.execute("SELECT * FROM lb_exhibitions WHERE title IS NOT NULL AND title!='' ORDER BY substr(date_start,7,4)||substr(date_start,4,2)||substr(date_start,1,2) DESC")]
    names = sorted(((a["name"], a["artist_id"]) for a in arts), key=lambda x: -len(x[0]))
    works = collections.defaultdict(list)
    for w in db.execute("SELECT w.*, e.title et, e.gallery, e.date_start FROM lb_exh_works w JOIN lb_exhibitions e USING(exh_id)"):
        t = w["title"] or ""
        for nm, aid in names:   # works carry "Artist Title" in one string; split on a known Lebriz artist name
            if t.startswith(nm + " ") or t == nm:
                works[aid].append({"t": t[len(nm):].strip(), "s": w["size"], "k": w["technique"], "i": w["image"], "e": w["exh_id"], "et": w["et"], "g": w["gallery"], "d": w["date_start"]}); break
    gal = {}
    for e in exhs:
        if not e["gallery"]: continue
        g = gal.setdefault(e["gallery"], {"n": e["gallery"], "a": e["address"], "c": e["city"], "x": 0, "last": None})
        g["x"] += 1; g["last"] = g["last"] or e["date_start"]
    meta = dict(db.execute("SELECT k,v FROM lb_meta").fetchall()) if db.execute("SELECT name FROM sqlite_master WHERE name='lb_meta'").fetchone() else {}
    idx = {"updated": meta.get("updated"),
           "artists": [{"id": a["artist_id"], "n": a["name"], "y": a["years"], "w": a["works_total"], "m": a["auction_catalogue_works"], "b": bool(a["bio"]), "ex": len(works.get(a["artist_id"], []))} for a in arts],
           "exhibitions": [{"id": e["exh_id"], "g": e["gallery"], "t": e["title"], "s": e["date_start"], "e": e["date_end"], "c": e["city"], "n": e["works_count"], "u": e["url"], "sn": e["snapshot"]} for e in exhs],
           "galleries": sorted(gal.values(), key=lambda g: -g["x"])}
    det = {}
    for a in arts:
        aid = a["artist_id"]
        det[aid] = {"bio": a["bio"], "bs": a["bio_source"], "url": a["url"], "sn": a["snapshot"],
            "series": [dict(n=r[0], c=r[1]) for r in db.execute("SELECT name,count FROM lb_series WHERE artist_id=? ORDER BY count DESC", (aid,))],
            "exh": [dict(k=r[0], d=r[1], t=r[2], x=r[3]) for r in db.execute("SELECT kind,date,text,exh_id FROM lb_artist_exh WHERE artist_id=? ORDER BY kind, date DESC", (aid,))],
            "works": works.get(aid, [])[:120]}
    import unicodedata
    def nk(x):
        x = (x or "").replace("I", "ı").replace("İ", "i").lower().replace("ı", "i")
        return "".join(c for c in unicodedata.normalize("NFD", x) if not unicodedata.combining(c)).strip()
    prices = {}
    try:
        for r in db.execute("SELECT artist, price, currency, auction, lot_no, auc_id FROM lb_auction_lots WHERE price > 0"):
            prices.setdefault(nk(re.sub(r"\(.*?\)", "", r[0])), []).append([r[1], r[2], r[3], r[4], r[5]])
    except sqlite3.OperationalError: pass
    json.dump(prices, open(os.path.join(OUT, "lebriz_prices.json"), "w", encoding="utf8"), ensure_ascii=False, separators=(",", ":"))
    idx["price_rows"] = sum(len(v) for v in prices.values())
    json.dump(idx, open(os.path.join(OUT, "lebriz_index.json"), "w", encoding="utf8"), ensure_ascii=False, separators=(",", ":"))
    json.dump(det, open(os.path.join(OUT, "lebriz_artists.json"), "w", encoding="utf8"), ensure_ascii=False, separators=(",", ":"))
    return len(arts), len(exhs), len(gal), sum(len(v) for v in works.values())
if __name__ == "__main__": print("lebriz export:", build())
