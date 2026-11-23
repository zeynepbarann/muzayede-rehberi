#!/usr/bin/env python3
"""Image door for the private bucket (Cloud Run).

The bucket stays private: nobody can list it or reach it directly. This service is the only reader. The site asks it for
  GET /i/<hash>.<ext>?u=<original image URL>   the full picture, object i/<hash>.<ext>
  GET /t/<hash>.<ext>?u=<original image URL>   a light copy (520px) for lists, made once from the full picture, kept as t/<hash>.jpg
<hash> is img_key(original URL), the same function the uploader (mirror_images.py) and the site use, so no lookup table exists.

Not mirrored yet? If ?u= really hashes to <hash>, the request is redirected to the original URL, so the site keeps working while
the backfill runs. A ?u= that does not match is ignored, so this cannot be used to redirect people to arbitrary sites.

Auth comes from the Cloud Run service account through the metadata server; there is no key file."""
import http.server, io, json, os, re, threading, time, urllib.error, urllib.parse, urllib.request
from PIL import Image, ImageOps

BUCKET = os.environ.get("BUCKET", "16-22")
# Comma-separated hosts allowed to embed images, e.g. "zeynepbarann.github.io,localhost". Empty = no check.
REFERERS = [h.strip().lower() for h in os.environ.get("ALLOWED_REFERERS", "").split(",") if h.strip()]
PATH = re.compile(r"^/(i|t)/([0-9a-f]{16})\.(jpg|jpeg|png|webp|gif|avif)$")
BOOK = re.compile(r"^/b/([a-z0-9-]{3,60})\.pdf$")
META = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
THUMB = 520
CACHE = "public, max-age=31536000, immutable"
_tok = {"v": None, "exp": 0}
_resize = threading.BoundedSemaphore(2)   # decoding large pictures is the only memory-hungry step


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


def gcs_open(name):
    """Open a bucket object; None if it does not exist."""
    api = "https://storage.googleapis.com/storage/v1/b/%s/o/%s?alt=media" % (BUCKET, urllib.parse.quote(name, safe=""))
    try:
        return urllib.request.urlopen(urllib.request.Request(api, headers={"Authorization": "Bearer " + token()}), timeout=20)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def gcs_keep(name, data):
    """Store a generated thumbnail, best effort; a failure only means it is made again next time."""
    q = urllib.parse.urlencode({"uploadType": "media", "name": name, "ifGenerationMatch": "0"})
    req = urllib.request.Request("https://storage.googleapis.com/upload/storage/v1/b/%s/o?%s" % (BUCKET, q), data=data, method="POST",
                                 headers={"Authorization": "Bearer " + token(), "Content-Type": "image/jpeg", "Cache-Control": CACHE})
    try:
        urllib.request.urlopen(req, timeout=30).read()
    except Exception:
        pass


def make_thumb(data):
    with _resize:
        im = Image.open(io.BytesIO(data))
        im.draft("RGB", (THUMB * 2, THUMB * 2))
        im = ImageOps.exif_transpose(im)
        im.thumbnail((THUMB, THUMB), Image.LANCZOS)
        if im.mode != "RGB":
            im = im.convert("RGB")
        out = io.BytesIO()
        im.save(out, "JPEG", quality=82, optimize=True, progressive=True)
        return out.getvalue()


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

    def image(self, body, ctype):
        self.send_response(200)
        self.send_header("Content-Type", ctype or "image/jpeg")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", CACHE)
        self.send_header("X-Content-Type-Options", "nosniff")
        origin = self.headers.get("Origin") or ""
        host = (urllib.parse.urlsplit(origin).hostname or "").lower()
        if origin and (not REFERERS or any(host == h or host.endswith("." + h) for h in REFERERS)):   # the image search compares pixels
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def referer_ok(self):
        ref = self.headers.get("Referer")
        if not REFERERS or not ref:  # browsers may strip the header; only a wrong one is refused
            return True
        host = (urllib.parse.urlsplit(ref).hostname or "").lower()
        return any(host == h or host.endswith("." + h) for h in REFERERS)

    def to_original(self, key, query, small):
        src = (urllib.parse.parse_qs(query).get("u") or [""])[0]
        if src.startswith(("http://", "https://")) and img_key(src) == key:
            if small:  # MüzayedeApp's host keeps its own light copy
                src = re.sub(r"(/Product/\d+)/1500/", r"\1/400/", src)
            return self.plain(302, "not mirrored yet", {"Location": src, "Cache-Control": "public, max-age=3600"})
        return self.plain(404, "not found")

    def book(self, name, download=False):
        """A catalogue PDF from books/ in the bucket, opened in the browser's own reader."""
        if not self.referer_ok():
            return self.plain(403, "forbidden")
        try:
            r = gcs_open("books/%s.pdf" % name)
            if not r:
                return self.plain(404, "not found")
            with r:
                size = r.headers.get("Content-Length")
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Disposition", '%s; filename="%s.pdf"' % ("attachment" if download else "inline", name))
                self.send_header("Cache-Control", "public, max-age=86400")
                self.send_header("X-Content-Type-Options", "nosniff")
                if size:
                    self.send_header("Content-Length", size)
                self.end_headers()
                if self.command != "HEAD":
                    while True:
                        chunk = r.read(1 << 18)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Exception:
            self.close_connection = True

    def fingerprints(self):
        """The image search index (hashjob/): only the site itself may read it."""
        origin = self.headers.get("Origin") or ""
        host = (urllib.parse.urlsplit(origin).hostname or "").lower()
        if not self.referer_ok() or (REFERERS and origin and not any(host == h or host.endswith("." + h) for h in REFERERS)):
            return self.plain(403, "forbidden")
        try:
            r = gcs_open("state/fingerprints.bin")
            if not r:
                return self.plain(404, "not ready")
            with r:
                body = r.read()
        except Exception:
            return self.plain(502, "storage unreachable")
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "public, max-age=600")
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        if u.path in ("/", "/healthz"):
            return self.plain(200, "ok")
        if u.path == "/f/fingerprints.bin":
            return self.fingerprints()
        b = BOOK.match(u.path)
        if b:
            return self.book(b.group(1), "dl=1" in u.query)
        m = PATH.match(u.path)
        if not m:
            return self.plain(404, "not found")
        if not self.referer_ok():
            return self.plain(403, "forbidden")
        kind, key, ext = m.groups()
        full = "i/%s.%s" % (key, ext)
        try:
            if kind == "t":
                tn = "t/%s.jpg" % key
                r = gcs_open(tn)
                if r:
                    with r:
                        return self.image(r.read(), "image/jpeg")
                r = gcs_open(full)
                if not r:
                    return self.to_original(key, u.query, True)
                with r:
                    data = r.read()
                try:
                    body = make_thumb(data)
                except Exception:   # a format Pillow cannot read: the full picture still works
                    return self.image(data, "image/jpeg")
                threading.Thread(target=gcs_keep, args=(tn, body), daemon=True).start()
                return self.image(body, "image/jpeg")
            r = gcs_open(full)
            if not r:
                return self.to_original(key, u.query, False)
            with r:
                return self.image(r.read(), r.headers.get("Content-Type"))
        except (BrokenPipeError, ConnectionResetError):
            self.close_connection = True
        except Exception:
            return self.plain(502, "storage unreachable")

    do_HEAD = do_GET


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    http.server.ThreadingHTTPServer(("0.0.0.0", port), H).serve_forever()
