"""Input-noise transforms for requests, and a noised copy of the holdout.

WHY SEPARATELY FROM REWORDING. `holdout_rw` tests whether the model survives a DIFFERENT WORDING
of the same question. This tests whether it survives the SAME wording typed badly -- typos, casing,
dropped punctuation, chat filler. Those are different failure surfaces and the rewording result
(five falsified explanations, every training-distribution change costing ~6 points) says nothing
about this one. Measure it before building a fix: arm E was cancelled because its baseline showed
the defect it targeted did not exist.

IDENTIFIERS MUST SURVIVE VERBATIM. A typo in the identifier makes the request ask about a symbol
that is not in the fixture, so the reference no longer answers it and the pair teaches a lie. This
is the same guard reword_train.py needed. Tokens that look like identifiers -- anything appearing
in the pair's own selector, plus camelCase/snake_case/dotted shapes -- are never corrupted.

REFERENCES ARE UNTOUCHED, so a noised eval needs no engine verification: only the request changes.

    python3 train/audit/noise.py eval        # -> holdout_noise/pairs/accepted-noise.jsonl
"""
import json, os, random, re, sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, HERE)
KEYS = {"a":"qsz","e":"wrd","i":"ouk","o":"ipl","u":"yij","s":"adw","t":"rfy","n":"bmh",
        "r":"etf","l":"ko","c":"xvd","d":"sfe","m":"n","p":"ol","g":"fh","h":"gj","b":"vn"}
IDENTISH = re.compile(r"[A-Za-z_][A-Za-z0-9_]*[._][A-Za-z0-9_]+|[a-z]+[A-Z]|_")

def protected(pair):
    """Tokens that must not be corrupted: everything named in the selector, plus identifier shapes."""
    keep = set(re.findall(r"[A-Za-z_][\w.]*", pair.get("css") or ""))
    return keep

def _typo(w, rnd):
    if len(w) < 4:
        return w
    i = rnd.randrange(1, len(w) - 1)
    mode = rnd.choice(("swap", "drop", "double", "near"))
    if mode == "swap":   return w[:i] + w[i+1] + w[i] + w[i+2:]
    if mode == "drop":   return w[:i] + w[i+1:]
    if mode == "double": return w[:i] + w[i] + w[i:]
    alt = KEYS.get(w[i].lower())
    return w[:i] + (rnd.choice(alt) if alt else w[i]) + w[i+1:] if alt else w

#: name -> (transform, description). Each is a thing a real person actually does.
def transforms():
    return {
      "typo":    (lambda s, p, r: _apply_words(s, p, r, 1), "one typo in a non-identifier word"),
      "typo2":   (lambda s, p, r: _apply_words(s, p, r, 2), "two typos"),
      # `lower` and `nopunct` MUST respect the protection set, like the typo transforms do.
      # They did not: `s.lower()` ignored `p` entirely, so "which file holds TYPEDEFS" became
      # "which file holds typedefs" and the reference `.mod#TYPEDEFS` no longer answered the
      # request. 35 of 320 noised holdout pairs were unanswerable that way, which inflated the
      # measured noise gap from 11.9 points to 20.0 and let a training arm appear to gain 4.4
      # points by learning to undo the corruption. The invariant at the top of this file was
      # correct; two of its own transforms broke it.
      "lower":   (lambda s, p, r: _map_words(s, p, str.lower), "lowercase, identifiers kept"),
      "nopunct": (lambda s, p, r: _map_words(s, p, lambda w: re.sub(r"[?.,'’]", "", w)),
                  "punctuation stripped, identifiers kept"),
      "filler":  (lambda s, p, r: r.choice(("pls ", "hey ", "um ", "quick one: ", "sorry, ")) + s,
                  "chat filler prefix"),
      "terse":   (lambda s, p, r: re.sub(r"^(where is|find|show me|take me to|which file)\s+", "", s,
                                         flags=re.I), "leading verb phrase dropped"),
    }

def _map_words(s, prot, fn):
    """Apply `fn` to every word that is not a protected identifier."""
    return " ".join(w if (w in prot or IDENTISH.search(w) or w.strip(".,?'") in prot) else fn(w)
                    for w in s.split())


def _apply_words(s, prot, rnd, n):
    words = s.split()
    cand = [i for i, w in enumerate(words)
            if len(w) >= 4 and w not in prot and not IDENTISH.search(w)]
    rnd.shuffle(cand)
    for i in cand[:n]:
        words[i] = _typo(words[i], rnd)
    return " ".join(words)

def noise(pair, kind, rnd):
    fn, _ = transforms()[kind]
    return fn(pair["nl"], protected(pair), rnd)

def main():
    import qualify, collections
    qualify.PAIRS_DIR = "holdout"
    pairs = qualify.load_pairs()
    out = os.path.join(HERE, "holdout_noise", "pairs")
    os.makedirs(out, exist_ok=True)
    rows, tally, unchanged = [], collections.Counter(), collections.Counter()
    kinds = list(transforms())
    for n, p in enumerate(pairs):
        rnd = random.Random("noise-%s" % p["id"])
        # The holdout's requests are already lowercase and unpunctuated, so `lower` and `nopunct`
        # are no-ops on most of them and `terse` only fires on a leading verb phrase. Assigning
        # transforms round-robin left 109 of 320 requests UNCHANGED -- a third of the suite
        # contributing no signal while looking like a measurement. Pick only from the transforms
        # that actually alter this request, preferring the round-robin one when it does.
        applies = [k for k in kinds if noise(p, k, random.Random("probe-%s-%s" % (p["id"], k))).strip()
                   != p["nl"].strip()]
        if not applies:
            unchanged["no transform applies"] += 1
            continue
        pref = kinds[n % len(kinds)]
        fallback = next((k for k in ("typo", "typo2") if k in applies), applies[0])
        kind = pref if pref in applies else fallback
        nl = noise(p, kind, rnd)
        if nl.strip() == p["nl"].strip():
            unchanged[kind] += 1
        # VERIFY the invariant rather than trusting the transform to respect it. Two transforms
        # already broke it once; a gate catches the next one too. Any name the reference selector
        # mentions must still appear verbatim in the noised request, or the pair is unanswerable.
        names = [x for x in re.findall(r"[A-Za-z_][\w.]*", p.get("css") or "")
                 if x in p["nl"]]
        if any(x not in nl for x in names):
            unchanged["REJECTED: identifier destroyed (%s)" % kind] += 1
            continue
        q = dict(p)
        q["nl"] = nl
        q["paraphrases"] = []
        q["noise"] = {"kind": kind, "from": p["nl"]}
        q["tags"] = sorted(set(p.get("tags") or []) | {"holdout-noise"})
        rows.append(q); tally[kind] += 1
    path = os.path.join(out, "accepted-noise.jsonl")
    with open(path, "w") as fh:
        for r in rows: fh.write(json.dumps(r) + "\n")
    print("wrote %d noised holdout requests -> %s" % (len(rows), path))
    print("by transform: %s" % dict(tally))
    print("no-op (transform did not change the request): %s" % (dict(unchanged) or "none"))
    print("\nexamples:")
    for r in rows[:8]:
        print("  %-9s %-46r -> %r" % (r["noise"]["kind"], r["noise"]["from"][:44], r["nl"][:52]))

if __name__ == "__main__" and (len(sys.argv) < 2 or sys.argv[1] == "eval"):
    main()


def train():
    """Noised TRAINING rows at constant volume.

    ROWS ARE HELD CONSTANT, like reword_train.py and for the same reason: adding noised copies
    would grow the corpus and confound the treatment with training volume, which is the mistake
    the pseudo-d3 and arity arms both made. Each pair keeps its canonical `nl` and its FIRST human
    paraphrase; only the SECOND paraphrase is replaced by a noised copy of the canonical. So the
    register the canonical carries survives (the lesson from the 12-point register loss), the row
    count matches arm D exactly, and D-vs-this is a pure treatment contrast.

    Measured first, per the arm E lesson: the settled model scores 80.3% on the clean holdout and
    60.3% on the noised one, and the control falls just as far (79.1% -> 60.6%). A 20-point,
    arm-independent gap is worth a training arm; the rewording gap's 6 points were not.
    """
    import collections, glob
    src = os.path.join(HERE, "workspace", "trainset-t5", "pairs.jsonl")
    dst_dir = os.path.join(HERE, "workspace", "trainset-t5-noise")
    os.makedirs(dst_dir, exist_ok=True)
    rows = [json.loads(l) for l in open(src)]
    kinds = list(transforms())
    tally, skipped = collections.Counter(), collections.Counter()
    for n, p in enumerate(rows):
        paras = list(p.get("paraphrases") or [])
        if len(paras) < 2:
            skipped["fewer than 2 paraphrases"] += 1
            continue
        rnd = random.Random("noisetrain-%s" % p.get("id", n))
        applies = [k for k in kinds
                   if noise(p, k, random.Random("probe-%s-%s" % (p.get("id", n), k))).strip()
                   != p["nl"].strip()]
        if not applies:
            skipped["no transform applies"] += 1
            continue
        pref = kinds[n % len(kinds)]
        fallback = next((k for k in ("typo", "typo2") if k in applies), applies[0])
        kind = pref if pref in applies else fallback
        paras[1] = noise(p, kind, rnd)
        p["paraphrases"] = paras
        p["noise"] = {"kind": kind, "replaced": "paraphrases[1]"}
        tally[kind] += 1
    dst = os.path.join(dst_dir, "pairs.jsonl")
    with open(dst, "w") as fh:
        for r in rows: fh.write(json.dumps(r) + "\n")
    print("wrote %d pairs -> %s" % (len(rows), dst))
    print("noised paraphrase by transform: %s" % dict(tally))
    print("left untouched: %s" % (dict(skipped) or "none"))

if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "train":
    train()
