"""Review packets: every pair with what its selector actually selects, for reading pair by pair.

    python3 review/review_packet.py [--sets train,val,eval,eval_t5] [--out workspace/review/packets]

One text file per language. Each pair shows its selector, its requests, the audit flags, and
the selected nodes as types and names: from oracle.Tree (documented semantics, built from the
engine's node export) when the oracle's node set equals the verified reference, otherwise
from the reference's file:line list, marked "engine lines".
"""
import argparse
import collections
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "review"))
import build_review as B  # noqa: E402
import oracle as O  # noqa: E402

_TREES = {}


def tree(fx):
    if fx not in _TREES:
        try:
            _TREES[fx] = O.Tree(fx)
        except (OSError, KeyError):
            _TREES[fx] = None
    return _TREES[fx]


def describe(p):
    """-> (source, summary lines) for the nodes the pair's selector selects."""
    t = tree(p["fixture"])
    ref = p.get("nodes") or []
    if t is not None:
        try:
            keys = t.select(O.parse(p["css"]))
        except Exception as e:  # noqa: BLE001 - the oracle refuses some shapes; fall back to lines
            keys, err = None, e
        if keys is not None:
            same = len(keys) == p.get("count")
            n = t.node
            by = collections.Counter((n[k]["type"], n[k]["name"] or "") for k in keys)
            parts = ["%s%s%s" % (ty, " " + nm if nm else "", " x%d" % c if c > 1 else "") for (ty, nm), c in by.most_common(8)]
            more = len(by) - 8
            where = sorted({os.path.basename(k[0]) for k in keys})
            src = "oracle" if same else "oracle (%d) != engine (%s)" % (len(keys), p.get("count"))
            return src, "; ".join(parts) + (" ... +%d more kinds" % more if more > 0 else "") + \
                "  [files: %s%s]" % (", ".join(where[:4]), " +%d" % (len(where) - 4) if len(where) > 4 else "")
    return "engine lines", ", ".join(ref)


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", default="train,val,eval,eval_t5")
    ap.add_argument("--out", default="workspace/review/packets")
    args = ap.parse_args(argv)
    wanted = set(args.sets.split(","))
    rows = []
    for p, path in B.load("train/pairs/accepted-*.jsonl"):
        rows.append(B.record(p, B.val_split(p["id"]), path))
    for p, path in B.load("pairs/accepted-*.jsonl") + B.load("pairs/pending-*.jsonl"):
        rows.append(B.record(p, "eval", path))
    for p, path in B.load("eval_t5/pairs/accepted-*.jsonl") + B.load("eval_t5/pairs/pending-*.jsonl"):
        rows.append(B.record(p, "eval_t5", path))
    rows = [r for r in rows if r["set"] in wanted]
    out = os.path.join(HERE, args.out)
    os.makedirs(out, exist_ok=True)
    by_lang = collections.defaultdict(list)
    for r in rows:
        by_lang[r["lang"]].append(r)
    for lang, rs in sorted(by_lang.items()):
        rs.sort(key=lambda r: (r["set"] != "eval" and r["set"] != "eval_t5", r["tier"] or 0, r["id"]))
        lines = []
        for r in rs:
            src, what = describe(r)
            lines.append("## %s [%s] %s T%s  %s   (%s nodes)" % (r["id"], r["set"], r["fixture"], r["tier"], r["css"], r.get("count")))
            lines.append("   selects (%s): %s" % (src, what))
            for k, t in enumerate(r["texts"]):
                fl = [f for f in r["flags"] if f[0] == k]
                lines.append("   %d %s%s" % (k, t, "".join("   <%s: %s>" % (f[1], f[2]) for f in fl)))
            if r.get("distractors"):
                lines.append("   near misses: %s" % " | ".join(r["distractors"]))
        with open(os.path.join(out, "%s.txt" % lang), "w") as fh:
            fh.write("\n".join(lines) + "\n")
        print("%-11s %4d pairs -> %s" % (lang, len(rs), os.path.relpath(os.path.join(out, "%s.txt" % lang), HERE)))


if __name__ == "__main__":
    main(sys.argv[1:])
