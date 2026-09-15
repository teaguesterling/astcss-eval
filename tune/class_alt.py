"""Language-spanning alternatives for every type-specific training selector.

Teague, 2026-09-15: `.catch:has(.call)` is preferred over `catch_clause:has(.call)`, but the
type-specific pairs are worth keeping -- "having specialized cases is good too". So nothing is
retired: for each accepted training pair whose selector names a grammar type, this adds a pair
that says the same thing in the card's class vocabulary.

The class is usually WIDER than the type (`.loop` covers `for_statement` and `while_statement`,
`.class` covers `create_table` and `create_view`, `.fn` covers lambdas), so the alternative is a
different question with its own node set, not a rewrite. Each candidate carries the type-specific
pair as its `contrast`, so the wording stage is told to make the difference explicit -- exactly
the contrast the corpus is missing today.

    python3 tune/class_alt.py --out workspace/classalt1
    python3 tune/gen_pairs.py word   --out workspace/classalt1
    python3 tune/gen_pairs.py verify --out workspace/classalt1 --batch classalt1
    python3 tune/gen_pairs.py filter --out workspace/classalt1 --batch classalt1

Gates here are the enumerate stage's: 1..50 nodes, every modifier load-bearing, a node set new to
training and not an eval answer. The wording stage and oracle.verify_batch do the rest.
"""
import argparse
import collections
import csv
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tune"))
import gen_pairs as G  # noqa: E402
import oracle as O  # noqa: E402
from oracle import render  # noqa: E402

BARE = G.re.compile(r"(?<![.#\w-])([a-z][a-z_]{3,})(?![\w-]*\()")
KEYWORDS = {"not", "has", "calls", "called", "by", "scope", "exported", "async", "typed", "decorated",
            "templated", "name", "receiver", "params", "signature", "annotation", "is", "referenced",
            "called-by", "callers"}


def type_classes():
    """node type -> card classes containing it, from the oracle cache (the engine's own class sets)."""
    out = collections.defaultdict(set)
    for fx in sorted(os.listdir(O.CACHE)):
        if not os.path.exists(O.cache(fx, "atoms.json")):
            continue
        types = {}
        with open(O.cache(fx, "nodes.csv"), newline="") as fh:
            for r in csv.DictReader(fh):
                types[(r["file_path"], int(r["node_id"]))] = r["type"]
        for cls, keys in json.load(open(O.cache(fx, "atoms.json"))).items():
            for k in keys:
                out[types[(k[0], int(k[1]))]].add(cls)
    return out


def class_form(css, t2c):
    """css with every bare type replaced by its class, or None if a type has no single class."""
    types = [t for t in BARE.findall(css) if t not in KEYWORDS and t in t2c]
    if not types:
        return None
    out = css
    for t in set(types):
        if len(t2c[t]) != 1:
            return None
        out = G.re.sub(r"(?<![.#\w-])%s(?![\w-])" % G.re.escape(t), next(iter(t2c[t])), out)
    return out if out != css else None


def variants(t, css2, p, seen):
    """The class form to use for this pair -> (css, struct, nodes, sha256), or None.

    The bare class form first. It is often much wider than the type it replaces (`.var` over a
    whole schema is hundreds of nodes), so when it misses the 1..50 bound the fallback scopes it
    to the named function or class the original pair's nodes all sit in -- still the card's
    vocabulary, still language-spanning, and a question a person would actually ask."""
    cands = []
    c = O.parse(css2)
    if c is not None and css2 not in seen:
        cands.append((css2, c))
    if c is not None and len(c["steps"]) == 1:
        orig = O.parse(p["css"])
        if orig is not None:
            nodes = t.select(orig)
            for sem, cls in ((O.CLS, ".class"), (O.FN, ".fn")):
                anc = {t.nearest(k, sem) for k in nodes}
                anc.discard(None)
                if len(anc) != 1:
                    continue
                name = t.node[anc.pop()]["name"]
                if not name or not G.re.match(r"^[A-Za-z_][\w]*$", name):
                    continue
                css3 = "%s#%s %s" % (cls, name, css2)
                c3 = O.parse(css3)
                if c3 is not None and css3 not in seen:
                    cands.append((css3, c3))
    for css, cc in cands:
        ref = t.select(cc)
        if 1 <= len(ref) <= 50:
            return css, cc, ref, t.digest(ref)
    return None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0, help="stop after N candidates (a smoke run)")
    args = ap.parse_args(argv)
    out = os.path.join(HERE, args.out) if not os.path.isabs(args.out) else args.out
    t2c = type_classes()
    _, taken, eval_css = G.taken_node_sets()
    trees, rows, skipped = {}, [], collections.Counter()
    seen_css = collections.defaultdict(set)
    for path in sorted(glob.glob(os.path.join(HERE, "train", "pairs", "accepted-*.jsonl"))):
        for line in open(path):
            p = json.loads(line)
            seen_css[p["fixture"]].add(p["css"])
    for path in sorted(glob.glob(os.path.join(HERE, "train", "pairs", "accepted-*.jsonl"))):
        for line in open(path):
            p = json.loads(line)
            fx = p["fixture"]
            css2 = class_form(p["css"], t2c)
            if css2 is None:
                continue
            if css2 in seen_css[fx]:
                skipped["already a pair on this fixture"] += 1
                continue
            if not os.path.exists(O.cache(fx, "atoms.json")):
                skipped["oracle cannot check it"] += 1
                continue
            t = trees.setdefault(fx, O.Tree(fx))
            cand = variants(t, css2, p, seen_css[fx])
            if cand is None:
                skipped["no in-bounds class form"] += 1
                continue
            css2, c2, ref, dg = cand
            if dg in taken:
                skipped["node set already in training"] += 1
                continue
            if css2 in eval_css:
                skipped["an eval answer"] += 1
                continue
            if any(t.select(r) == ref for r in O.relaxed(c2)):
                skipped["a modifier is not load-bearing"] += 1
                continue
            # The type-specific original is the first distractor: it is exactly the confusion the
            # pair must teach apart. A second comes from the relaxations, which already differ.
            dis = [O.parse(p["css"])]
            for r in O.relaxed(c2):
                if t.select(r) != ref and render(r) != css2:
                    dis.append(r)
                    break
            if len(dis) < 2 or dis[0] is None:
                skipped["fewer than 2 distractors"] += 1
                continue
            lang = G.lang_of(fx) if fx.split("-")[0] in G.LANG_BY_PREFIX else "python"
            ex = sorted(ref)[:2]
            rows.append({"id": "tr-%s-t%d-cl%04d" % (lang, O.tier(c2), len(rows)), "tier": O.tier(c2),
                         "fixture": fx, "lang": lang, "family": "class-form", "css": css2, "struct": c2,
                         "distractor_structs": dis, "distractors": [render(d) for d in dis],
                         "gloss": G.gloss(c2, lang), "pred": {"count": len(ref), "sha256": dg},
                         "examples": ["%s:%s  %s" % (os.path.basename(f), t.node[(f, nid)]["start_line"],
                                                     G.source_line(f, t.node[(f, nid)]["start_line"]))
                                      for f, nid in ex],
                         "contrast": {"css": p["css"], "gloss": G.gloss(O.parse(p["css"]), lang), "id": p["id"]}})
            seen_css[fx].add(css2)
            taken.add(dg)
            if args.limit and len(rows) >= args.limit:
                break
    os.makedirs(os.path.join(out, "candidates"), exist_ok=True)
    dest = os.path.join(out, "candidates", "selectors.jsonl")
    with open(dest, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("%d candidates -> %s" % (len(rows), os.path.relpath(dest, HERE)))
    print("tiers %s" % dict(collections.Counter(r["tier"] for r in rows)))
    print("languages %s" % dict(collections.Counter(r["lang"] for r in rows)))
    print("skipped: %s" % dict(skipped))
    for r in rows[:10]:
        print("   %-26s %-30s (vs %s)" % (r["id"], r["css"], r["contrast"]["css"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
