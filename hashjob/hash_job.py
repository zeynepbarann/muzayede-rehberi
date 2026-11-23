#!/usr/bin/env python3
"""Fingerprints for the image search: one small record for every picture in the private bucket.

Reads i/<key>.<ext>, makes a 128-bit fingerprint of the whole picture, and keeps the result in the bucket as
  state/fingerprints.bin    24 bytes per picture: 8 bytes of the name, 16 bytes of fingerprint
The image door serves that file to the site; the search itself runs in the visitor's browser, so an uploaded picture never
leaves their device. A picture already fingerprinted is skipped, so a daily run only reads what is new.

The fingerprint must stay identical to imgPrint() in template.html.
Environment: BUCKET (default 16-22), HASH_MINUTES (default 330), HASH_WORKERS (default 8).
"""
import concurrent.futures as cf, io, json, os, re, struct, threading, time, urllib.error, urllib.parse, urllib.request
from PIL import Image, ImageFile, ImageOps

BUCKET = os.environ.get("BUCKET", "16-22")
MINUTES = float(os.environ.get("HASH_MINUTES", "330"))
WORKERS = int(os.environ.get("HASH_WORKERS", "8"))
OBJECT = "state/fingerprints.bin"
META = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
API = "https://storage.googleapis.com/storage/v1/b/%s/o" % BUCKET
NAME = re.compile(r"^i/([0-9a-f]{16})\.\w+$")
ImageFile.LOAD_TRUNCATED_IMAGES = True
Image.MAX_IMAGE_PIXELS = 120_000_000
_tok, _lock = {"v": None, "exp": 0}, threading.Lock()


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def token():
    with _lock:
        if not _tok["v"] or time.time() > _tok["exp"] - 60:
            d = json.load(urllib.request.urlopen(urllib.request.Request(META, headers={"Metadata-Flavor": "Google"}), timeout=10))
            _tok.update(v=d["access_token"], exp=time.time() + d.get("expires_in", 300))
        return _tok["v"]


def call(url, data=None, ctype=None, tries=4):
    for i in range(tries):
        try:
            h = {"Authorization": "Bearer " + token()}
            if ctype:
                h["Content-Type"] = ctype
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h, method="POST" if data is not None else "GET"), timeout=120) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404 or i == tries - 1:
                raise
        except Exception:
            if i == tries - 1:
                raise
        time.sleep(2 * (i + 1))


def names():
    out, page = {}, ""
    while True:
        q = {"prefix": "i/", "fields": "nextPageToken,items(name)", "maxResults": 1000}
        if page:
            q["pageToken"] = page
        d = json.loads(call(API + "?" + urllib.parse.urlencode(q)))
        for it in d.get("items", []):
            m = NAME.match(it["name"])
            if m:
                out[m.group(1)] = it["name"]
        page = d.get("nextPageToken")
        if not page:
            return out


def fingerprint(im):
    im = ImageOps.exif_transpose(im).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    raw = bg.convert("RGB").resize((64, 64), Image.BOX).tobytes()
    g = [0.299 * raw[i] + 0.587 * raw[i + 1] + 0.114 * raw[i + 2] for i in range(0, len(raw), 3)]

    def cells(cols, rows):
        out = []
        for y in range(rows):
            y0, y1 = y * 64 // rows, (y + 1) * 64 // rows
            for x in range(cols):
                x0, x1 = x * 64 // cols, (x + 1) * 64 // cols
                s = sum(g[j * 64 + i] for j in range(y0, y1) for i in range(x0, x1))
                out.append(s / ((y1 - y0) * (x1 - x0)))
        return out
    a, b, v = cells(9, 8), cells(8, 9), 0
    for y in range(8):
        for x in range(8):
            v = v << 1 | (a[y * 9 + x] < a[y * 9 + x + 1])
    for y in range(8):
        for x in range(8):
            v = v << 1 | (b[y * 8 + x] < b[(y + 1) * 8 + x])
    return v.to_bytes(16, "big")


def one(key, name):
    try:
        data = call(API + "/" + urllib.parse.quote(name, safe="") + "?alt=media")
        with Image.open(io.BytesIO(data)) as im:
            return key, fingerprint(im)
    except Exception:
        return key, None


def load():
    try:
        b = call(API + "/" + urllib.parse.quote(OBJECT, safe="") + "?alt=media")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {}
        raise
    return {b[i:i + 8].hex(): b[i + 8:i + 24] for i in range(0, len(b) - len(b) % 24, 24)}


def save(fp):
    body = b"".join(bytes.fromhex(k) + v for k, v in sorted(fp.items()))
    call("https://storage.googleapis.com/upload/storage/v1/b/%s/o?%s" % (BUCKET, urllib.parse.urlencode({"uploadType": "media", "name": OBJECT})), data=body, ctype="application/octet-stream")


def main():
    stop = time.time() + MINUTES * 60
    fp, all_names = load(), names()
    todo = [(k, n) for k, n in all_names.items() if k not in fp]
    log("%d pictures in the bucket, %d already done, %d to read" % (len(all_names), len(fp), len(todo)))
    done = bad = 0
    last = time.time()
    with cf.ThreadPoolExecutor(WORKERS) as ex:
        for i in range(0, len(todo), 400):
            if time.time() > stop:
                log("time budget reached; the next run continues")
                break
            for key, v in ex.map(lambda t: one(*t), todo[i:i + 400]):
                done += 1
                if v:
                    fp[key] = v
                else:
                    bad += 1
            if time.time() - last > 300:
                save(fp)
                last = time.time()
                log("%d read, %d unreadable, %d fingerprints saved" % (done, bad, len(fp)))
    save(fp)
    log("finished this run: %d read, %d unreadable, %d fingerprints" % (done, bad, len(fp)))


if __name__ == "__main__":
    main()
