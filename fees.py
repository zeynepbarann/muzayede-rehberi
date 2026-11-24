#!/usr/bin/env python3
"""Buyer's commission and KDV, read from the auction and lot pages scrape.py already downloads.

data/fees.json (export.py copies it into data/lots.json as "fees"):
  {"v": 1, "kdv": 20, "houses": {"<site>": FEE}, "auctions": {"<site>|<auction name>": FEE}, "cur": {"<site>|<auction name>": "USD"}}
  "cur" lists the auctions priced in another currency than TL; finished records keep their auction name, so their prices are read in it too.
  FEE = {"c": 15, "k": "all"|"fee"|"in"|"", "src": "<the house's own words>", "at": "YYYY-MM-DD"}
c = commission in percent. k says how KDV is charged:
  "all"  on hammer price + commission (what the house's own "Toplam Maliyet" shows)
  "fee"  on the commission only ("%10 komisyon + KDV")
  "in"   already included ("KDV dahil")
  ""     the house does not mention KDV
A house that states nothing has no entry, and the site then shows no total.
"""
import datetime as dt, html, json, os, re

HERE = os.path.dirname(os.path.abspath(__file__))
PATH = os.path.join(HERE, "data", "fees.json")
KDV = 20

PCT = r"(\d{1,2}(?:[.,]\d{1,2})?)"
NEAR = [re.compile(r"(?i)komisyon\w*[^.%\d]{0,45}%\s?" + PCT), re.compile(r"(?i)%\s?" + PCT + r"[^.%\d]{0,45}komisyon"),
        re.compile(r"(?i)komisyon\w*[^.%\d]{0,25}" + PCT + r"\s?%"), re.compile(r"(?i)" + PCT + r"\s?%[^.%\d]{0,45}komisyon"),
        re.compile(r"(?i)hizmet bedeli[^.%\d]{0,45}%\s?" + PCT), re.compile(r"(?i)%\s?" + PCT + r"[^.%\d]{0,45}hizmet bedeli")]
LOT = re.compile(r"Komisyon:\s*%?\s?" + PCT + r"\s?%?")


def text(page):
    page = re.sub(r"(?s)<(script|style)[^>]*>.*?</\1>", " ", page or "")
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", page))).strip()


def today():
    return dt.date.today().isoformat()


NONE = re.compile(r"(?i)komisyon\w*\s+(?:al[ıi]nmamaktad[ıi]r|almamaktad[ıi]r|almayacakt[ıi]r|yoktur|bulunmamaktad[ıi]r)|komisyonsuz")
KDV_ON_FEE = re.compile(r"(?i)%\s?\d{1,2}(?:[.,]\d{1,2})?\s*\+\s*k\.?\s?d\.?\s?v|komisyon\w*\s*\+\s*k\.?\s?d\.?\s?v")
KDV_IN = re.compile(r"(?i)k\.?\s?d\.?\s?v\.?\s*dahil")
KDV_ANY = re.compile(r"(?i)\bk\.?\s?d\.?\s?v\b|katma de[gğ]er vergisi")


def read_terms(t):
    """Commission and KDV from a house's own words in an auction description; None when it states neither."""
    c, src = None, ""
    for rx in NEAR:
        for m in rx.finditer(t):
            if re.search(r"(?i)iptal|iade|cezai|gecikme|cayma|faiz", t[max(0, m.start() - 60):m.end() + 20]):
                continue   # a cancellation or late-payment charge, not the buyer's commission
            v = float(m.group(1).replace(",", "."))
            if 0 <= v <= 35:
                c, src = v, t[max(0, m.start() - 40):m.end() + 80]
                break
        if c is not None:
            break
    if c is None:
        m = NONE.search(t)
        if m:   # "Müzayedemizde komisyon alınmamaktadır": the price plus any KDV is the total
            c, src = 0.0, t[max(0, m.start() - 40):m.end() + 80]
    if c is None:
        return None
    k = "in" if KDV_IN.search(t) else "fee" if KDV_ON_FEE.search(t) else "all" if KDV_ANY.search(t) else ""
    return {"c": c, "k": k, "src": src.strip()[:220], "at": today()}


def auction_terms(page):
    """The description part of an auction page (before the lot list)."""
    t = text(page)
    i = t.find("Lot No")
    return read_terms(t[:i] if i > 0 else t)


def lot_terms(page):
    """A lot page of the houses on their own sites: "Komisyon: 15%", and "K.D.V.: ... Toplam Maliyet" once it has a price."""
    t = text(page)
    m = LOT.search(t)
    if not m:
        return read_terms(t)
    return {"c": float(m.group(1).replace(",", ".")), "k": "all" if re.search(r"K\.D\.V\.:\s*[\d.]", t) else "", "src": m.group(0), "at": today()}


def load():
    try:
        with open(PATH, encoding="utf8") as f:
            d = json.load(f)
        if d.get("v") == 1:
            return d
    except Exception:
        pass
    return {"v": 1, "kdv": KDV, "houses": {}, "auctions": {}, "cur": {}}


def currency(site, auction, d=None):
    """The currency an auction is priced in; TL unless the house said otherwise."""
    return ((d or load()).get("cur") or {}).get("%s|%s" % (site, (auction or "").strip()), "TL")


def save(found_houses, found_auctions, found_cur=None):
    """Merge this run's findings; what a house said before stays until it says something new."""
    d = load()
    d["kdv"] = KDV
    d["houses"].update({k: v for k, v in found_houses.items() if v})
    d["auctions"].update({k: v for k, v in found_auctions.items() if v})
    cur = d.setdefault("cur", {})
    for k, v in (found_cur or {}).items():
        if v and v != "TL":
            cur[k] = v
        else:
            cur.pop(k, None)
    tmp = PATH + ".tmp"
    with open(tmp, "w", encoding="utf8") as f:
        json.dump(d, f, ensure_ascii=False, indent=0, sort_keys=True)
    os.replace(tmp, PATH)
    return d
