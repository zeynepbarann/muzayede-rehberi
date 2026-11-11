#!/usr/bin/env python3
"""Temporary helper: print the structure of web pages. Usage: probe.py URL [URL...]; KEYS env = regex for text contexts."""
import sys, re, os, json, html, urllib.request
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36"
KEYS = os.environ.get("KEYS") or r"geçmiş|Geçmiş|GEÇMİŞ|sonuçlan|Sonuçlan|Açıklama|Ölçü|Boyut|Eser Bilgi|product-detail|description"
for url in sys.argv[1:]:
    print("=" * 100, "\nURL", url)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json", "Accept-Language": "tr-TR,tr;q=0.9", "X-Requested-With": "XMLHttpRequest"})
        with urllib.request.urlopen(req, timeout=40) as r:
            print("STATUS", r.status, "| FINAL", r.geturl()); t = r.read().decode("utf8", "replace")
    except Exception as e:
        print("ERROR", repr(e)); continue
    print("LENGTH", len(t))
    try:
        j = json.loads(t)
        if isinstance(j, dict) and isinstance(j.get("products"), list):
            print("KEYS:", list(j)); print("N:", len(j["products"])); print("FIRST:", json.dumps({k: v for k, v in (j["products"] or [{}])[0].items() if k != "images"}, ensure_ascii=False)[:1500])
        elif isinstance(j, dict) and isinstance(j.get("auctions"), list):
            print("AUCTIONS:", [(a.get("id"), a.get("saleNo"), a.get("name"), a.get("finishedAt"), a.get("isFinished")) for a in j["auctions"]], {k: v for k, v in j.items() if k != "auctions"})
        else: print("JSON:", json.dumps(j, ensure_ascii=False)[:2000])
        continue
    except Exception: pass
    print("TITLE", (re.search(r"<title>(.*?)</title>", t, re.S) or [None, ""])[1].strip()[:200])
    hrefs = list(dict.fromkeys(re.findall(r'href="([^"#]+)"', t)))
    print("HREFS:", [h for h in hrefs if re.search(r"muzayede|gecmis|sonuc|arsiv|urun|lot", h, re.I)][:80])
    for m in list(re.finditer(KEYS, t))[:12]:
        print("CTX>", re.sub(r"\s+", " ", t[max(0, m.start() - 250): m.start() + 700]))
