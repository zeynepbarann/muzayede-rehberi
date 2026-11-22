#!/usr/bin/env python3
"""The daily refresh as a Cloud Run job: nobody's computer has to be on.

Each run:
  1. clones the repository (code and the published data files),
  2. fetches the database and the image-mirror progress from the private bucket (state/…); on the very first run there is no
     database yet, so seed_db.py rebuilds one from the data files,
  3. runs the same steps as refresh.sh: new links, daily scan, finished auctions, image mirror, export, per-artist shards,
  4. checks the result is sane (never publish a shrunken archive), commits "Daily refresh <date>" and pushes,
  5. puts the database and mirror progress back in the bucket.

Because the code is cloned at run time, changing a script in the repository needs no redeploy of this job.

Environment:
  BUCKET            private bucket for state and images          (default 16-22)
  REPO              GitHub repository "owner/name"               (default zeynepbarann/muzayede-rehberi)
  GH_TOKEN          GitHub token with Contents read/write on REPO (from Secret Manager); without it nothing is pushed
  JOB_MODE          "refresh" (default), "probe" = only check which auction sites answer from here,
                    "images" = only copy images into the bucket (no scan, no database, no push),
                    or "lebriz" = pull every artist's Lebriz catalogue from the Internet Archive and publish it
  DRY_RUN=1         run everything but do not push and do not write state back
  HISTORY_MINUTES / MIRROR_MINUTES   time budgets (default 30 / 30)
Standard library + git. Access to the bucket comes from the job's own service account; there is no key file."""
import datetime, json, os, shutil, subprocess, sys, threading, time, urllib.error, urllib.parse, urllib.request

BUCKET = os.environ.get("BUCKET", "16-22")
REPO = os.environ.get("REPO", "zeynepbarann/muzayede-rehberi")
TOKEN = os.environ.get("GH_TOKEN", "").strip()
DRY = os.environ.get("DRY_RUN") == "1"
WORK = os.environ.get("WORKDIR", "/tmp/work")
META = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"
STATE = ["auctions.db", "mirror_state.json"]   # files that live in the bucket between runs
_tok = {"v": None, "exp": 0}


def log(*a):
    print(datetime.datetime.now().strftime("%H:%M:%S"), *a, flush=True)


def gtoken():
    if _tok["v"] and time.time() < _tok["exp"] - 60:
        return _tok["v"]
    d = json.load(urllib.request.urlopen(urllib.request.Request(META, headers={"Metadata-Flavor": "Google"}), timeout=10))
    _tok.update(v=d["access_token"], exp=time.time() + d.get("expires_in", 300))
    return _tok["v"]


def gcs_get(name, dest):
    """Download bucket object to a file. False if it does not exist."""
    url = "https://storage.googleapis.com/storage/v1/b/%s/o/%s?alt=media" % (BUCKET, urllib.parse.quote(name, safe=""))
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"Authorization": "Bearer " + gtoken()}), timeout=600) as r, open(dest + ".part", "wb") as f:
            shutil.copyfileobj(r, f, 1 << 20)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise
    os.replace(dest + ".part", dest)
    return True


def gcs_put(name, src):
    q = urllib.parse.urlencode({"uploadType": "media", "name": name})
    size = os.path.getsize(src)
    with open(src, "rb") as f:
        req = urllib.request.Request("https://storage.googleapis.com/upload/storage/v1/b/%s/o?%s" % (BUCKET, q), data=f, method="POST",
                                     headers={"Authorization": "Bearer " + gtoken(), "Content-Type": "application/octet-stream", "Content-Length": str(size)})
        urllib.request.urlopen(req, timeout=900).read()


def run(args, timeout=None, check=False, quiet=False):
    """Run a step inside the clone. Returns True on success; a failing step is reported and the run goes on (like refresh.sh)."""
    shown = " ".join(a if "x-access-token" not in a else "<repo url>" for a in args)
    if not quiet:
        log("$", shown)
    try:
        p = subprocess.run(args, cwd=WORK, timeout=timeout)
    except subprocess.TimeoutExpired:
        log("  stopped after %ss (continues next run): %s" % (timeout, shown)); return False
    if p.returncode and check:
        raise SystemExit("step failed: " + shown)
    if p.returncode:
        log("  exit %d: %s" % (p.returncode, shown))
    return p.returncode == 0


def counts():
    def n(name, key=None):
        p = os.path.join(WORK, "data", name)
        if not os.path.exists(p):
            return 0
        with open(p, encoding="utf8") as f:
            d = json.load(f)
        return len(d[key] if key else d)
    return {"lots": n("lots.json", "lots"), "past": n("past.json")}


def probe():
    """Which auction sites answer from this network? (Some refuse data-centre addresses.)"""
    sys.path.insert(0, WORK)
    import scrape
    hosts = ["https://%s/" % h for h in getattr(scrape, "MUZAYEDEAPP", [])] + ["https://www.muzayedeapp.com/", "https://www.artvela.com/", "https://www.sanatsalmuzayede.com/", "https://www.artam.com/"]
    ok = 0
    for u in hosts:
        try:
            r = urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": getattr(scrape, "UA", "Mozilla/5.0"), "Accept-Language": "tr-TR,tr;q=0.9"}), timeout=25)
            body = r.read(4000); ok += 1
            log("  OK   %s  %s  %d bytes read" % (r.status, u, len(body)))
        except Exception as e:
            log("  FAIL %s  %s" % (u, e))
    log("probe: %d of %d sites answered" % (ok, len(hosts)))
    return 0


def images_only():
    """Copy images into the bucket and nothing else: no scan, no database, no push. Progress is saved every 5 minutes."""
    name, path = "mirror_state.json", os.path.join(WORK, "mirror_state.json")
    log("state %s: %s" % (name, "restored" if gcs_get("state/" + name, path) else "not in the bucket yet"))
    stop = threading.Event()

    def save():
        if os.path.exists(path):
            gcs_put("state/" + name, path)

    def saver():
        while not stop.wait(300):
            try:
                save()
            except Exception as e:
                log("progress not saved this time:", e)
    threading.Thread(target=saver, daemon=True).start()
    minutes = os.environ.get("MIRROR_MINUTES", "570")
    ok = run([sys.executable, "mirror_images.py", "--minutes", minutes], timeout=int(float(minutes) * 60) + 300)
    stop.set()
    save()
    log("image copy finished" if ok else "image copy stopped early; the next run resumes")
    return 0 if ok else 1


def publish_paths(message, paths):
    """Commit the given paths and push, replaying on top of anything pushed meanwhile (the daily refresh does)."""
    git = lambda *a, **k: run(["git", "-c", "user.name=16/22 archive", "-c", "user.email=archive@users.noreply.github.com"] + list(a), quiet=True, **k)
    git("add", "-A", *paths)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=WORK).returncode == 0:
        return False
    git("commit", "-q", "-m", message, check=True)
    url = "https://x-access-token:%s@github.com/%s.git" % (TOKEN, REPO)
    for i in range(5):
        if git("fetch", "-q", "--depth", "50", url, "main") and git("rebase", "-q", "FETCH_HEAD") and git("push", "-q", url, "HEAD:main"):
            return True
        run(["git", "rebase", "--abort"], quiet=True)
        time.sleep(10 * (i + 1))
    raise SystemExit("could not push the Lebriz catalogues")


def lebriz_only():
    """Pull every artist's Lebriz catalogue from the Internet Archive. Resumable: finished artists are kept in the bucket,
    and results are published every 20 minutes. An artist the archive could not be reached for is retried next run."""
    extra = os.environ.get("LEBRIZ_EXTRA") == "1"   # artists with surviving pictures who are missing from the Lebriz list
    pname = "lebriz_extra_progress.json" if extra else "lebriz_progress.json"
    prog = os.path.join(WORK, pname)
    gcs_get("state/" + pname, prog)
    done = set(json.load(open(prog, encoding="utf8"))) if os.path.exists(prog) else set()
    cat = os.path.join(WORK, "data", "lebriz_catalog")
    os.makedirs(cat, exist_ok=True)
    have = lambda i: os.path.exists(os.path.join(cat, "%d.json" % i))
    with open(os.path.join(WORK, "data", "lebriz_index.json"), encoding="utf8") as f:
        artists = sorted(json.load(f)["artists"], key=lambda a: -(a.get("w") or 0))
    only = [int(x) for x in os.environ.get("LEBRIZ_IDS", "").split(",") if x.strip()]
    todo = only or [a["id"] for a in artists if a["id"] not in done]
    known = {a["id"] for a in artists}
    if extra:
        sys.path.insert(0, WORK)
        import lebriz_pull
        count = {}
        for k in lebriz_pull.image_map():
            i = int(k.split(":")[0])
            count[i] = count.get(i, 0) + 1
        todo = only or sorted((i for i in count if i not in known and i not in done), key=lambda i: -count[i])

    def write_extra():
        """data/lebriz_extra.json: the added artists the site should list. Without a name there is nothing to show them under."""
        out = []
        for name in os.listdir(cat):
            with open(os.path.join(cat, name), encoding="utf8") as f:
                c = json.load(f)
            if c.get("id") not in known and c.get("name") and c.get("with_images"):
                out.append({"id": c["id"], "n": c["name"], "w": c.get("total") or len(c.get("works") or [])})
        with open(os.path.join(WORK, "data", "lebriz_extra.json"), "w", encoding="utf8") as f:
            json.dump(sorted(out, key=lambda a: a["id"]), f, ensure_ascii=False, separators=(",", ":"))
    deadline = time.time() + float(os.environ.get("LEBRIZ_MINUTES", "1320")) * 60
    log("lebriz: %d artists, %d to pull" % (len(artists), len(todo)))
    last, n = time.time(), 0

    def checkpoint():
        if DRY:
            return
        with open(prog, "w", encoding="utf8") as f:
            json.dump(sorted(done), f)
        gcs_put("state/" + pname, prog)
        if extra:
            write_extra()
        if TOKEN and publish_paths("Lebriz catalogues: %d %sartists pulled" % (len(done), "added " if extra else ""), ["data/lebriz_catalog"] + (["data/lebriz_extra.json"] if extra else [])):
            log("published, %d artists finished" % len(done))
    for aid in todo:
        if time.time() > deadline:
            log("time budget reached; the next run resumes")
            break
        run([sys.executable, "lebriz_pull.py", "--ids", str(aid)], timeout=3000)
        n += 1
        if have(aid):
            with open(os.path.join(cat, "%d.json" % aid), encoding="utf8") as f:
                if not json.load(f).get("partial"):   # the archive gave no page list: try this artist again next run
                    done.add(aid)
        if time.time() - last > 1200:
            checkpoint()
            last = time.time()
    checkpoint()
    works = 0
    for name in os.listdir(cat):
        with open(os.path.join(cat, name), encoding="utf8") as f:
            works += len(json.load(f).get("works") or [])
    log("lebriz finished this run: %d tried, %d catalogue files, %d works" % (n, len(os.listdir(cat)), works))
    return 0


def main():
    mode = os.environ.get("JOB_MODE", "refresh")
    log("mode=%s repo=%s bucket=%s dry=%s push=%s" % (mode, REPO, BUCKET, DRY, bool(TOKEN)))
    if os.path.isdir(WORK) and not os.environ.get("KEEP_WORKDIR"):
        shutil.rmtree(WORK)
    if not os.path.isdir(WORK):
        subprocess.run(["git", "clone", "--depth", "1", "https://github.com/%s.git" % REPO, WORK], check=True)
    if mode == "probe":
        return probe()
    if mode == "images":
        return images_only()
    if mode == "lebriz":
        return lebriz_only()
    local = os.environ.get("SKIP_GCS") == "1"   # for trying the steps on a laptop
    if not local:
        for name in STATE:
            log("state %s: %s" % (name, "restored" if gcs_get("state/" + name, os.path.join(WORK, name)) else "not in the bucket yet"))
    before = counts()
    if not os.path.exists(os.path.join(WORK, "auctions.db")):
        run([sys.executable, "seed_db.py"], check=True)
    steps = os.environ.get("STEPS", "sources,scan,history,mirror,export,shards").split(",")
    hm, mm = os.environ.get("HISTORY_MINUTES", "30"), os.environ.get("MIRROR_MINUTES", "30")
    if "sources" in steps:
        run([sys.executable, "add_sources.py"], timeout=1800)
    if "scan" in steps:
        run([sys.executable, "scrape.py"], timeout=3600)
    if "history" in steps:
        run([sys.executable, "history_mapp.py", "--minutes", hm], timeout=int(float(hm) * 60) + 300)
    if "mirror" in steps and not local:
        run([sys.executable, "mirror_images.py", "--minutes", mm], timeout=int(float(mm) * 60) + 300)
    if "export" in steps:
        run([sys.executable, "export.py"], check=True)
    if "shards" in steps and os.path.exists(os.path.join(WORK, "shard_past.py")):
        run([sys.executable, "shard_past.py"])
    after = counts()
    log("lots %d -> %d, finished lots %d -> %d" % (before["lots"], after["lots"], before["past"], after["past"]))
    # the archive only ever grows; a big drop means a step went wrong, and publishing it would erase history from the site
    sane = after["past"] >= before["past"] * 0.9 and (after["lots"] > 0 or before["lots"] == 0)
    if not sane:
        log("REFUSING TO PUBLISH: the result lost data. Nothing was pushed and the stored database was left as it was.")
        return 2
    if DRY or local:
        log("dry run: nothing pushed, state not written back"); return 0
    for name in STATE:
        p = os.path.join(WORK, name)
        if os.path.exists(p):
            gcs_put("state/" + name, p); log("state %s saved (%d kB)" % (name, os.path.getsize(p) // 1024))
    if not TOKEN:
        log("no GH_TOKEN: data was refreshed and state saved, but nothing was pushed to GitHub"); return 0
    git = lambda *a, **k: run(["git", "-c", "user.name=16/22 refresh", "-c", "user.email=refresh@users.noreply.github.com"] + list(a), **k)
    git("add", "-A", "data", "index.html", "sources.json", quiet=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=WORK).returncode == 0:
        log("nothing changed; no commit"); return 0
    git("commit", "-q", "-m", "Daily refresh " + datetime.date.today().isoformat(), check=True)
    url = "https://x-access-token:%s@github.com/%s.git" % (TOKEN, REPO)
    if not git("push", "-q", url, "HEAD:main", quiet=True):
        # someone pushed meanwhile (the add-link workflow does): replay our commit on top and try once more
        git("fetch", "-q", "--depth", "50", url, "main", quiet=True)
        git("rebase", "FETCH_HEAD", check=True)
        git("push", "-q", url, "HEAD:main", quiet=True, check=True)
    log("pushed"); return 0


if __name__ == "__main__":
    sys.exit(main())
