#!/usr/bin/env python3
"""Image door for the private bucket (Cloud Run).

The bucket stays private: nobody can list it or reach it directly. This service is the only reader. The site asks it for
  GET /i/<hash>.<ext>?u=<original image URL>
and it streams the object  i/<hash>.<ext>  from the bucket. <hash> is img_key(original URL), the same function the uploader
(mirror_images.py) and the site use, so no lookup table is needed anywhere.

Not mirrored yet? If ?u= really hashes to <hash>, the request is redirected to the original URL, so the site keeps working while
the backfill runs. A ?u= that does not match is ignored, so this cannot be used to redirect people to arbitrary sites.

Standard library only. Auth comes from the Cloud Run service account through the metadata server; there is no key file."""
import http.server, json, os, re, time, urllib.error, urllib.parse, urllib.request

BUCKET = os.environ.get("BUCKET", "16-22")
# Comma-separated hosts allowed to embed images, e.g. "zeynepbarann.github.io,localhost". Empty = no check.
REFERERS = [h.strip().lower() for h in os.environ.get("ALLOWED_REFERERS", "").split(",") if h.strip()]
PATH = re.compile(r"^/i/([0-9a-f]{16})\.(jpg|jpeg|png|webp|gif|avif)$")
META = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
_tok = {"v": None, "exp": 0}


def img_key(url):
    """16 hex chars from the URL: two 32-bit FNV-1a hashes with different seeds. Must match mirror_images.py and template.html."""
    out = []
    for seed in (0x811C9DC5, 0x01000193):
        h = seed
        for b in url.encode("utf8"):
            h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
        out.append("%08x" % h)
    return "".join(out)


def token():
    if _tok["v"] and time.time() < _tok["exp"] - 60:
        return _tok["v"]
    r = urllib.request.urlopen(urllib.request.Request(META, headers={"Metadata-Flavor": "Google"}), timeout=5)
    d = json.load(r)
    _tok.update(v=d["access_token"], exp=time.time() + d.get("expires_in", 300))
    return _tok["v"]


class H(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # Cloud Run already logs requests
        pass

    def plain(self, code, text, extra=None):
        b = text.encode()
        self.send_response(code)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(b)

    def referer_ok(self):
        ref = self.headers.get("Referer")
        if not REFERERS or not ref:  # browsers may strip the header; only a wrong one is refused
            return True
        host = (urllib.parse.urlsplit(ref).hostname or "").lower()
        return any(host == h or host.endswith("." + h) for h in REFERERS)

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        if u.path in ("/", "/healthz"):
            return self.plain(200, "ok")
        m = PATH.match(u.path)
        if not m:
            return self.plain(404, "not found")
        if not self.referer_ok():
            return self.plain(403, "forbidden")
        name = u.path[1:]
        api = "https://storage.googleapis.com/storage/v1/b/%s/o/%s?alt=media" % (BUCKET, urllib.parse.quote(name, safe=""))
        try:
            r = urllib.request.urlopen(urllib.request.Request(api, headers={"Authorization": "Bearer " + token()}), timeout=20)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                src = (urllib.parse.parse_qs(u.query).get("u") or [""])[0]
                if src.startswith(("http://", "https://")) and img_key(src) == m.group(1):
                    return self.plain(302, "not mirrored yet", {"Location": src, "Cache-Control": "public, max-age=3600"})
                return self.plain(404, "not found")
            return self.plain(502, "storage error %s" % e.code)
        except Exception:
            return self.plain(502, "storage unreachable")
        with r:
            self.send_response(200)
            self.send_header("Content-Type", r.headers.get("Content-Type") or "image/jpeg")
            if r.headers.get("Content-Length"):
                self.send_header("Content-Length", r.headers["Content-Length"])
            else:
                self.send_header("Connection", "close")
                self.close_connection = True
            # an object never changes once written (its name is a hash of where it came from), so it can be cached for good
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if self.command == "HEAD":
                return
            while True:
                chunk = r.read(65536)
                if not chunk:
                    break
                self.wfile.write(chunk)

    do_HEAD = do_GET


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    http.server.ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
