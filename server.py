#!/usr/bin/env python3
"""Local web app: python3 server.py [port]  -> http://localhost:8000"""
import http.server, sys, export
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        b = export.build().encode()
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers(); self.wfile.write(b)
port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
print(f"http://localhost:{port}"); http.server.ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
