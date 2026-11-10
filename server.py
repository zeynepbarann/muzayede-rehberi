#!/usr/bin/env python3
"""Local web app: python3 server.py [port] -> http://localhost:8000
Serves the HTML shell (rebuilt from template.html per request) and static assets (data/*.json, favicon). Run export.py to refresh data."""
import http.server, sys, os, export
HERE = os.path.dirname(os.path.abspath(__file__))
class H(http.server.SimpleHTTPRequestHandler):
    def __init__(s, *a, **k): super().__init__(*a, directory=HERE, **k)
    def do_GET(self):
        p = self.path.split("?")[0]
        if p in ("/", "/index.html"):
            b = export.build(write_data=False).encode()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers(); self.wfile.write(b)
        elif (p.startswith("/data/") and p.endswith(".json")) or p == "/favicon.svg": super().do_GET()
        else: self.send_error(404)
port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
print(f"http://localhost:{port}"); http.server.ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
