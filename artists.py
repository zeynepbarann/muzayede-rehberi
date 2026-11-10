#!/usr/bin/env python3
"""Unify artist name variants into canonical keys.
Lebriz names are preferred anchors. Manual overrides live in artist_aliases.json.
Conservative: never merge two different given names that share a surname.
"""
import json, os, re, unicodedata, collections
HERE = os.path.dirname(os.path.abspath(__file__))
ALIASES = os.path.join(HERE, "artist_aliases.json")

TR = str.maketrans({"I": "ı", "İ": "i", "Ş": "ş", "Ğ": "ğ", "Ü": "ü", "Ö": "ö", "Ç": "ç"})
FOLD = str.maketrans({"ş": "s", "ğ": "g", "ü": "u", "ö": "o", "ç": "c", "ı": "i", "â": "a", "î": "i", "û": "u"})
YEAR = re.compile(r"\((?:\s*(?:d|ö|o|dogum|doğum)?\.?\s*)?(?:1[6-9]\d{2}|20\d{2})(?:\s*[-–—]\s*(?:1[6-9]\d{2}|20\d{2}))?\s*\)", re.I)
YEAR2 = re.compile(r"\[(?:\s*(?:d|ö|o)?\.?\s*)?(?:1[6-9]\d{2}|20\d{2})(?:\s*[-–—]\s*(?:1[6-9]\d{2}|20\d{2}))?\s*\]", re.I)
LEADING_YEAR = re.compile(r"^(?:1[6-9]\d{2}|20\d{2})\b")
# trailing life dates without parens: "Ali Demir 1931-2015"
TRAIL = re.compile(r"\s+(?:d\.)?\s*(?:1[6-9]\d{2}|20\d{2})(?:\s*[-–—]\s*(?:1[6-9]\d{2}|20\d{2}))\s*$", re.I)
PUNCT = re.compile(r"[^\w\s]", re.UNICODE)
SPACE = re.compile(r"\s+")
INITIAL = re.compile(r"^[a-z]$")
# titles / noise prefixes
PREFIX = re.compile(r"^(?:(?:ressam|heykeltiras|heykeltıraş|hattat|fotografci|fotoğrafçı|mimar|prof(?:esör)?|dr|doç(?:ent)?)\.?\s+)+", re.I)
GENERIC = re.compile(
    r"^(imza okunamad[ıi]|imzas[ıi]z|imzali|imzalı|anonim|osmanl[iı]ca|karma|koleksiyon|various|unknown|"
    r"takim|takım|lotu|adet |el isi|el işi|el oymasi|el oyması)", re.I
)

def tr_lower(s):
    return (s or "").translate(TR).lower()

def clean(s):
    s = tr_lower(s or "")
    s = re.sub(r"\([^)]*\)", " ", s)
    s = re.sub(r"\[[^\]]*\]", " ", s)
    s = TRAIL.sub(" ", s)
    s = s.replace("`", "'").replace("’", "'").replace("ʻ", "'")
    s = PREFIX.sub("", s)
    s = PUNCT.sub(" ", s)
    return SPACE.sub(" ", s).strip()

def fold(s):
    s = clean(s).translate(FOLD)
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if not unicodedata.combining(c))

# Allow typo-merge of given names only for insertion or a small set of letter swaps (d/t, b/p…).
_SWAPS = {frozenset(x) for x in ("dt","bp","vw","qk","ck","yi","sz","ae")}
def typo_given_ok(a, b):
    if a == b: return True
    if abs(len(a) - len(b)) == 1 and (a in b or b in a) and min(len(a), len(b)) >= 4: return True
    if len(a) == len(b) and min(len(a), len(b)) >= 4 and lev(a, b, 1) == 1:
        diffs = [(ca, cb) for ca, cb in zip(a, b) if ca != cb]
        return len(diffs) == 1 and frozenset(diffs[0]) in _SWAPS
    return False

def tokens(s):
    return [t for t in fold(s).split() if t]

def is_personish(name):
    """Skip object titles, years-as-names, very long lot titles."""
    if not name or len(name) > 80: return False
    if LEADING_YEAR.search(name.strip()): return False
    t = tokens(name)
    if not t: return False
    if GENERIC.match(fold(name)): return False
    # a person name is typically 1–5 tokens, mostly letters, not a sentence
    if len(t) > 6: return False
    if sum(len(x) for x in t) < 3: return False
    return True

def lev(a, b, maxd=2):
    if abs(len(a) - len(b)) > maxd: return maxd + 1
    if a == b: return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[-1] + 1, prev[j - 1] + (ca != cb)))
        if min(cur) > maxd: return maxd + 1
        prev = cur
    return prev[-1]

def load_aliases():
    if not os.path.exists(ALIASES):
        return {"overrides": {}, "do_not_merge": []}
    return json.load(open(ALIASES, encoding="utf8"))

def nice_name(forms, counts, lebriz=None):
    if lebriz: return lebriz
    # prefer mixed-case, then most frequent, then longest (more complete, no years)
    def score(s):
        stripped = YEAR.sub("", YEAR2.sub("", s)).strip() or s
        mixed = int(any(c.islower() for c in s) and any(c.isupper() for c in s))
        no_year = int(not re.search(r"\d{4}", s))
        return (mixed, no_year, counts.get(s, 0), len(stripped))
    return max(forms, key=score)

def build(names, lebriz_artists=None, counts=None):
    """names: iterable of raw artist strings.
    lebriz_artists: list of {'n','id'}
    counts: raw name -> frequency (for display choice)
    Returns dict raw -> {n, v, lb, person}
    and list of clusters.
    """
    aliases = load_aliases()
    overrides = {k: v for k, v in (aliases.get("overrides") or {}).items()}
    blocked = set()
    for a, b in aliases.get("do_not_merge") or []:
        blocked.add(frozenset([fold(a), fold(b)]))

    counts = counts or collections.Counter(names)
    raw_unique = list(dict.fromkeys([n for n in names if n and str(n).strip()]))

    # Lebriz index
    lb_by_fold, lb_by_last = {}, collections.defaultdict(list)
    for a in lebriz_artists or []:
        f = fold(a["n"])
        if not f: continue
        lb_by_fold.setdefault(f, a)
        toks = tokens(a["n"])
        if toks: lb_by_last[toks[-1]].append((f, a, toks))

    parent = {}
    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b, why):
        if not a or not b or a == b: return False
        if frozenset([a, b]) in blocked: return False
        ra, rb = find(a), find(b)
        if ra == rb: return False
        parent[rb] = ra
        return True

    # Every name starts as its fold key (or itself if not personish — isolated)
    keys = {}  # raw -> cluster key (fold or 'raw:'+raw)
    for n in raw_unique:
        if n in overrides:
            keys[n] = fold(overrides[n]) or ("ov:" + fold(overrides[n]))
            continue
        if is_personish(n):
            keys[n] = fold(n) or ("raw:" + n)
        else:
            keys[n] = "raw:" + n  # isolated, no clustering
        parent.setdefault(keys[n], keys[n])

    # Exact fold already unified via same key.

    # Map fold -> raws (personish only)
    by_fold = collections.defaultdict(list)
    for n in raw_unique:
        k = keys[n]
        if k.startswith("raw:"): continue
        if k.startswith("ov:"): continue
        by_fold[k].append(n)

    person_folds = [f for f in by_fold if f]

    # Initial + surname: "a atilla" / "a. atilla" vs "ali atilla"
    last_index = collections.defaultdict(list)  # last -> list of (fold, toks)
    for f in person_folds:
        t = f.split()
        if t: last_index[t[-1]].append((f, t))

    def given_compatible(g1, g2):
        """True if two given-name token lists can be the same person."""
        if not g1 or not g2:
            return bool(g1) == bool(g2) or (len(g1) + len(g2) == 1 and (g1 or g2) and INITIAL.match((g1 or g2)[0]))
        # pad initials: ['h'] vs ['husamettin'] ; ['a','s'] vs ['ali','sami']
        if len(g1) != len(g2):
            # allow dropping a middle initial: ['mehmet','a'] vs ['mehmet']
            longer, shorter = (g1, g2) if len(g1) > len(g2) else (g2, g1)
            if len(longer) - len(shorter) == 1 and all(INITIAL.match(x) or x == 's' for x in longer if x not in shorter):
                # weak; only if the shared tokens are compatible
                pass
            else:
                return False
        i = j = 0
        # greedy pair
        # simplify: zip min length after expanding initials
        def expand_ok(a, b):
            if a == b: return True
            if INITIAL.match(a) and b.startswith(a) and len(b) >= 3: return True
            if INITIAL.match(b) and a.startswith(b) and len(a) >= 3: return True
            if typo_given_ok(a, b): return True
            return False
        if len(g1) == len(g2):
            return all(expand_ok(a, b) for a, b in zip(g1, g2))
        # different lengths: all short-side tokens must match a unique long-side token in order
        long, short = (g1, g2) if len(g1) > len(g2) else (g2, g1)
        j = 0
        for a in short:
            found = False
            while j < len(long):
                if expand_ok(a, long[j]):
                    found = True; j += 1; break
                j += 1
            if not found: return False
        return True

    # initial expansion: only when the surname is unique OR only one compatible full given name
    for last, group in last_index.items():
        if len(group) < 2: continue
        # try to merge initials into a unique full name
        full = [x for x in group if any(len(t) >= 3 for t in x[1][:-1])]
        inits = [x for x in group if x[1][:-1] and all(len(t) <= 2 for t in x[1][:-1])]
        for fi, ft in inits:
            cands = [x for x in full if given_compatible(ft[:-1], x[1][:-1])]
            # also other inits
            if len(cands) == 1:
                union(cands[0][0], fi, "initial")
            elif not cands:
                # two initial forms of same pattern
                peers = [x for x in inits if x[0] != fi and given_compatible(ft[:-1], x[1][:-1])]
                for p in peers:
                    union(fi, p[0], "init-init")

    # typo merge: same last name (or 1-edit if last is long), compatible given, typo in a long token
    folds_list = person_folds
    # index by last name for typo candidates
    for last, group in last_index.items():
        if len(group) < 2: continue
        for i, (f1, t1) in enumerate(group):
            for f2, t2 in group[i + 1:]:
                if not given_compatible(t1[:-1], t2[:-1]): continue
                # if both have full (len>=3) given names that differ by more than typo, skip — given_compatible already handles
                # require at least one token typo-close
                if f1 == f2: continue
                d = lev(f1, f2, 2)
                # only 1 edit if both reasonably long, 2 edits if very long and same given start
                minlen = min(len(f1), len(f2))
                if d == 1 and minlen >= 8:
                    union(f1, f2, "typo1")
                elif d == 2 and minlen >= 14 and t1[:-1] and t2[:-1] and t1[0] == t2[0] and len(t1[0]) >= 4:
                    union(f1, f2, "typo2")

    # typo in surname (rare): last names dist 1, length >= 6, given names equal and full
    lasts = list(last_index)
    for i, a in enumerate(lasts):
        if len(a) < 6: continue
        for b in lasts[i + 1:]:
            if len(b) < 6 or abs(len(a) - len(b)) > 1 or lev(a, b, 1) > 1: continue
            for f1, t1 in last_index[a]:
                for f2, t2 in last_index[b]:
                    g1, g2 = t1[:-1], t2[:-1]
                    if g1 and g2 and g1 == g2 and all(len(x) >= 3 for x in g1):
                        union(f1, f2, "surname-typo")

    # Apply overrides into their target cluster
    for n, canon in overrides.items():
        fk, ck = keys.get(n), "ov:" + fold(canon)
        if fk: union(ck, fk, "override")
        parent.setdefault(ck, ck)

    # Attach Lebriz anchors (by fold, typo, or unique surname+initial)
    lb_attach = {}  # cluster root -> lebriz artist
    for f, raws in by_fold.items():
        a = lb_by_fold.get(f)
        if not a and len(f) >= 9:
            close = [x for x in lb_by_fold if abs(len(x) - len(f)) <= 1 and lev(x, f, 1) <= 1]
            if len(close) == 1: a = lb_by_fold[close[0]]
        if not a:
            t = f.split()
            if t and t[-1] in lb_by_last:
                cands = [x for x in lb_by_last[t[-1]] if given_compatible(t[:-1], x[2][:-1])]
                if len(cands) == 1: a = cands[0][1]
        if a:
            r = find(f)
            # don't attach two different lebriz ids to one cluster
            if r in lb_attach and lb_attach[r]["id"] != a["id"]:
                continue
            lb_attach[r] = a

    # Also index override keys
    for n, canon in overrides.items():
        ck = "ov:" + fold(canon)
        a = lb_by_fold.get(fold(canon))
        if a: lb_attach[find(ck)] = a

    # Build clusters
    clusters = collections.defaultdict(list)  # root -> raw names
    for n in raw_unique:
        clusters[find(keys[n])].append(n)

    out = {}  # raw -> record
    cluster_info = []
    for root, raws in clusters.items():
        lb = lb_attach.get(root)
        display = nice_name(raws, counts, lb["n"] if lb else None)
        # if override target exists as a string, prefer that spelling
        for n in raws:
            if n in overrides:
                display = overrides[n]
                break
            # also if this cluster is ov:X, use the override value
        if root.startswith("ov:"):
            # find override value
            for n, v in overrides.items():
                if fold(v) == root[3:] or "ov:" + fold(v) == root:
                    display = v; break
        variants = sorted(set(raws), key=lambda s: (-counts.get(s, 0), s))
        rec = {"n": display, "v": variants, "lb": lb["id"] if lb else None, "c": sum(counts.get(x, 0) for x in raws)}
        cluster_info.append(rec)
        for n in raws:
            out[n] = rec

    cluster_info.sort(key=lambda r: -r["c"])
    return out, cluster_info

def apply_to_lots(lots, past, lebriz_artists):
    names = [l.get("artist") for l in lots] + [p.get("artist") for p in past]
    counts = collections.Counter(n for n in names if n)
    mp, clusters = build(names, lebriz_artists, counts)
    for l in lots:
        raw = l.get("artist") or ""
        rec = mp.get(raw)
        if rec and rec["n"] != raw:
            l["artist_raw"] = raw
            l["artist"] = rec["n"]
        if rec and rec["lb"]:
            l["lb_id"] = rec["lb"]
    for p in past:
        raw = p.get("artist") or ""
        rec = mp.get(raw)
        if rec and rec["n"] != raw:
            p["artist_raw"] = raw
            p["artist"] = rec["n"]
        if rec and rec["lb"]:
            p["lb_id"] = rec["lb"]
    artists = []
    seen = set()
    for rec in clusters:
        k = rec["n"]
        if k in seen: continue
        seen.add(k)
        artists.append(rec)
    raw_n = len(set(n for n in names if n))
    return {
        "raw": raw_n,
        "canon": len(artists),
        "merged": raw_n - len(artists),
        "artists": artists,
    }, mp

if __name__ == "__main__":
    import sqlite3
    db = sqlite3.connect(os.path.join(HERE, "auctions.db"))
    names = [r[0] for r in db.execute("SELECT artist FROM lots") if r[0]]
    names += [r[0] for r in db.execute("SELECT artist FROM price_history") if r[0]]
    lb = []
    p = os.path.join(HERE, "data", "lebriz_index.json")
    if os.path.exists(p):
        lb = json.load(open(p, encoding="utf8")).get("artists") or []
    counts = collections.Counter(names)
    mp, clusters = build(names, lb, counts)
    raw = len(set(names))
    canon = len({id(c) for c in mp.values()})  # wrong
    recs, seen = [], set()
    for r in mp.values():
        if id(r) in seen: continue
        seen.add(id(r)); recs.append(r)
    print(f"raw {raw} -> canon {len(recs)} (collapsed {raw-len(recs)})")
    merged = [r for r in recs if len(r["v"]) > 1]
    print(f"clusters with variants: {len(merged)}")
    for r in sorted(merged, key=lambda x: -len(x["v"]))[:25]:
        print(f"  {r['n']}  lb={r['lb']}  n={r['c']}  variants={r['v'][:8]}")
