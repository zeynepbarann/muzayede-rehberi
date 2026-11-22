#!/usr/bin/env python3
"""Copy every image the archive knows about into the private bucket, so pictures outlive the auctions they came from.

  python3 mirror_images.py                 # mirror what is new, newest data first
  python3 mirror_images.py --minutes 25    # stop after ~25 minutes (resumes next run)
  python3 mirror_images.py --dry-run       # only count what would be copied; needs no key

Reads image URLs from data/lots.json and the data/past*.json files, downloads each once and uploads it as
  i/<img_key(url)>.<ext>
in the bucket. The name is a hash of the source URL, so the site and the image door (imgproxy/main.py) can work it out
from the URL alone. What is already done is remembered in mirror_state.json (not committed).

Inside Google Cloud (cloudjob/) it needs nothing: the job's own identity is used. On any other computer it needs a
service-account key that may only create objects in the bucket (role: Storage Object Creator):
  GCS_KEY     path to the key file   (default ~/.config/16-22-uploader.json)
  GCS_BUCKET  bucket name            (default 16-22)
Standard library plus the `openssl` program (to sign the login request); no pip packages."""
import base64, json, os, subprocess, sys, tempfile, time, urllib.error, urllib.parse, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BUCKET = os.environ.get("GCS_BUCKET", "16-22")
KEY = os.path.expanduser(os.environ.get("GCS_KEY", "~/.config/16-22-uploader.json"))
STATE = os.path.join(HERE, "mirror_state.json")
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
EXT = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp", "gif": "image/gif", "avif": "image/avif"}
TYPE_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "image/gif": "gif", "image/avif": "avif"}
MAX_BYTES = 25 * 1024 * 1024


def img_key(url):
    """16 hex chars from the URL: two 32-bit FNV-1a hashes with different seeds. Must match imgproxy/main.py and template.html."""
    out = []
    for seed in (0x811C9DC5, 0x01000193):
        h = seed
        for b in url.encode("utf8"):
            h = ((h ^ b) * 0x01000193) & 0xFFFFFFFF
        out.append("%08x" % h)
    return "".join(out)


def img_ext(url):
    """Extension as the site guesses it from the URL (no network): the path's own if it is an image type, else jpg."""
    e = urllib.parse.urlsplit(url).path.rsplit(".", 1)[-1].lower() if "." in urllib.parse.urlsplit(url).path else ""
    return e if e in EXT else "jpg"


def obj_name(url):
    return "i/%s.%s" % (img_key(url), img_ext(url))


def all_urls():
    """Image URLs in the data files, live lots first, then finished auctions. Order is stable; duplicates dropped."""
    seen, out = set(), []

    def add(u):
        if isinstance(u, str) and u.startswith(("http://", "https://")) and u not in seen:
            seen.add(u); out.append(u)
    def load(name):
        p = os.path.join(HERE, "data", name)
        if not os.path.exists(p):
            return None
        with open(p, encoding="utf8") as f:
            return json.load(f)
    d = load("lots.json") or {}
    for l in d.get("lots", []):
        for u in l.get("images") or []:
            add(u)
    for name in ("past.json", "past_archive.json", "past_archive_mapp.json"):
        for x in load(name) or []:
            add(x.get("image"))
    # Lebriz closed in 2023: its catalogue pictures survive only in the Internet Archive, so keep our own copy
    cat = os.path.join(HERE, "data", "lebriz_catalog")
    for name in sorted(os.listdir(cat)) if os.path.isdir(cat) else []:
        for w in (load(os.path.join("lebriz_catalog", name)) or {}).get("works") or []:
            add(w.get("i"))
    return out


def b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=")


METADATA = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"


def metadata_token():
    """Inside Google Cloud (the daily job) access comes from the job's own identity: no key file at all."""
    d = json.load(urllib.request.urlopen(urllib.request.Request(METADATA, headers={"Metadata-Flavor": "Google"}), timeout=5))
    return d["access_token"], int(time.time()) + int(d.get("expires_in", 300))


def access_token():
    """Key file if there is one (a computer outside Google); otherwise the cloud identity.
    Key login without pip packages: build the JWT, let openssl sign it, swap it for an access token."""
    if not os.path.exists(KEY):
        return metadata_token()
    with open(KEY, encoding="utf8") as f:
        k = json.load(f)
    now = int(time.time())
    claim = {"iss": k["client_email"], "scope": "https://www.googleapis.com/auth/devstorage.read_write",
             "aud": "https://oauth2.googleapis.com/token", "iat": now, "exp": now + 3600}
    msg = b64(json.dumps({"alg": "RS256", "typ": "JWT"}).encode()) + b"." + b64(json.dumps(claim).encode())
    fd, pem = tempfile.mkstemp(suffix=".pem")
    try:
        os.chmod(pem, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(k["private_key"])
        sig = subprocess.run(["openssl", "dgst", "-sha256", "-sign", pem], input=msg, capture_output=True, check=True).stdout
    finally:
        os.remove(pem)
    body = urllib.parse.urlencode({"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": (msg + b"." + b64(sig)).decode()}).encode()
    d = json.load(urllib.request.urlopen(urllib.request.Request("https://oauth2.googleapis.com/token", data=body), timeout=30))
    return d["access_token"], now + int(d.get("expires_in", 3600))


def fetch(url):
    r = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "image/avif,image/webp,image/*,*/*;q=0.8"}), timeout=40)
    with r:
        ctype = (r.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        data = r.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("too large")
    if len(data) < 200 or not (ctype.startswith("image/") or ctype in ("application/octet-stream", "binary/octet-stream", "")):
        raise ValueError("not an image (%s, %d bytes)" % (ctype or "no type", len(data)))
    return data, ctype if ctype in TYPE_EXT else EXT[img_ext(url)]


def upload(name, data, ctype, tok):
    """Create the object only if it is not there yet (ifGenerationMatch=0). True = written, False = it already existed."""
    q = urllib.parse.urlencode({"uploadType": "media", "name": name, "ifGenerationMatch": "0"})
    req = urllib.request.Request("https://storage.googleapis.com/upload/storage/v1/b/%s/o?%s" % (BUCKET, q), data=data, method="POST",
                                 headers={"Authorization": "Bearer " + tok, "Content-Type": ctype, "Cache-Control": "public, max-age=31536000, immutable"})
    try:
        urllib.request.urlopen(req, timeout=120).read()
        return True
    except urllib.error.HTTPError as e:
        if e.code == 412:
            return False
        raise


def main(argv):
    dry = "--dry-run" in argv
    minutes = float(argv[argv.index("--minutes") + 1]) if "--minutes" in argv else 0
    limit = int(argv[argv.index("--limit") + 1]) if "--limit" in argv else 0
    state = {"done": [], "failed": {}}
    if os.path.exists(STATE):
        with open(STATE, encoding="utf8") as f:
            state.update(json.load(f))
    done, failed = set(state["done"]), state["failed"]
    urls = all_urls()
    # a URL that failed three times is left alone (the source has usually deleted it); delete mirror_state.json to retry all
    todo = [u for u in urls if img_key(u) not in done and failed.get(img_key(u), 0) < 3]
    print("images: %d known, %d mirrored, %d to copy, %d given up" % (len(urls), len(done), len(todo), sum(1 for v in failed.values() if v >= 3)))
    if dry:
        for u in todo[:5]:
            print("  would copy", u, "->", obj_name(u))
        return 0
    try:
        tok, exp = access_token()
    except Exception as e:
        print("no access to the bucket (no key file at %s and not running inside Google Cloud): %s" % (KEY, e))
        return 1
    t0, n, wrote, last_host, last_at = time.time(), 0, 0, "", 0.0

    def save():
        tmp = STATE + ".tmp"
        with open(tmp, "w", encoding="utf8") as f:
            json.dump({"done": sorted(done), "failed": failed}, f)
        os.replace(tmp, STATE)
    try:
        for u in todo:
            if (minutes and time.time() - t0 > minutes * 60) or (limit and n >= limit):
                break
            if time.time() > exp - 300:
                tok, exp = access_token()
            host = urllib.parse.urlsplit(u).netloc
            gap = 1.2 if "archive.org" in host else 0.25
            if host == last_host and time.time() - last_at < gap:  # be gentle with each source's server
                time.sleep(gap)
            last_host, last_at, k = host, time.time(), img_key(u)
            n += 1
            try:
                data, ctype = fetch(u)
                wrote += upload(obj_name(u), data, ctype, tok)
                done.add(k); failed.pop(k, None)
            except Exception as e:
                failed[k] = failed.get(k, 0) + 1
                print("  failed (%d): %s: %s" % (failed[k], u[:90], e))
            if n % 50 == 0:
                save()
                print("  %d tried, %d written, %.0fs" % (n, wrote, time.time() - t0))
    finally:
        save()
    print("done: %d tried, %d written, %d left" % (n, wrote, len(todo) - n))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
