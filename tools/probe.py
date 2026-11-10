#!/usr/bin/env python3
"""Temporary helper: print the structure of web pages (for writing a scraper). Usage: probe.py URL [URL...]"""
import sys, re, json, html, urllib.request
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36"
for url in sys.argv[1:]:
    print("=" * 100, "\nURL", url)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,application/json", "Accept-Language": "tr-TR,tr;q=0.9", "X-Requested-With": "XMLHttpRequest"})
        with urllib.request.urlopen(req, timeout=40) as r:
            print("STATUS", r.status, "| TYPE", r.headers.get("content-type"), "| FINAL", r.geturl())
            b = r.read()
    except Exception as e:
        print("ERROR", repr(e)); continue
    t = b.decode("utf8", "replace"); print("LENGTH", len(t))
    try:
        j = json.loads(t); print("JSON:", json.dumps(j, ensure_ascii=False, indent=1)[:6000]); continue
    except Exception: pass
    print("TITLE", (re.search(r"<title>(.*?)</title>", t, re.S) or [None, ""])[1].strip()[:200], "| Bakımdayız:", "Bakımdayız" in t)
    hrefs = list(dict.fromkeys(re.findall(r'href="([^"#]+)"', t)))
    print("HREFS (auction/lot-like):", [h for h in hrefs if re.search(r"muzayede|lot|eser|urun|auction|product", h, re.I)][:60])
    print("SCRIPT SRC:", re.findall(r'<script[^>]+src="([^"]+)"', t)[:30])
    for s in re.findall(r"<script[^>]*>(.*?)</script>", t, re.S):
        for line in s.splitlines():
            if re.search(r"ajax|axios|fetch\(|api/|get-|url\s*:|\.json|lots?|endpoint|route", line, re.I):
                print("SCRIPT>", line.strip()[:400])
    for kw in ["lot", "product", "item", "card"]:
        m = re.search(rf'class="[^"]*\b{kw}[^"]*"', t, re.I)
        if m:
            print(f"--- first class~{kw} context ---\n", t[max(0, m.start() - 300): m.start() + 2500]); break
    print("--- data-attributes sample:", list(dict.fromkeys(re.findall(r'\bdata-[\w-]+', t)))[:60])
