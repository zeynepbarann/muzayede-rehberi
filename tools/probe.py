#!/usr/bin/env python3
"""Temporary helper: print the structure of web pages. Usage: probe.py URL [URL...]"""
import sys, re, os, json, urllib.request
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129 Safari/537.36"
KEYS = os.environ.get("KEYS") or r"geçmiş|Geçmiş|sonuçlan|Sonuçlan|satıldı|Satıldı|SATILDI|tamamlan|bitti|Bitti|api/|ws\.artvela"
for url in sys.argv[1:]:
    print("=" * 100, "\nURL", url)
    body = None
    if url.startswith("POST:"): url, raw = url[5:].split("|", 1); body = raw.encode()
    try:
        req = urllib.request.Request(url, data=body, headers={"User-Agent": UA, "Accept": "text/html,application/json,*/*", "Accept-Language": "tr-TR,tr;q=0.9", **({"Content-Type": "application/json"} if body else {})})
        with urllib.request.urlopen(req, timeout=40) as r:
            print("STATUS", r.status, "| FINAL", r.geturl()); t = r.read().decode("utf8", "replace")
    except Exception as e:
        print("ERROR", repr(e)); continue
    print("LENGTH", len(t))
    try:
        j = json.loads(t); print("JSON:", json.dumps(j, ensure_ascii=False)[:3000]); continue
    except Exception: pass
    if url.split("?")[0].endswith(".js"):
        print("JS URLS:", sorted(set(re.findall(r"[\"'`]((?:https?://[a-z0-9.\-]+)?/(?:api|v\d)[A-Za-z0-9_\-/{}.:]*)[\"'`]", t)))[:150]); continue
    print("TITLE", (re.search(r"<title>(.*?)</title>", t, re.S) or [None, ""])[1].strip()[:200])
    print("SCRIPTS:", re.findall(r'<script[^>]+src="([^"]+)"', t)[:15])
    hrefs = list(dict.fromkeys(re.findall(r'href="([^"#]+)"', t)))
    print("HREFS:", hrefs[:120])
    for m in list(re.finditer(KEYS, t))[:10]:
        print("CTX>", re.sub(r"\s+", " ", t[max(0, m.start() - 250): m.start() + 500]))
