"""Do the frozen training labels still reproduce under the engine in use now?

usage: python3 tune/check_train_labels.py [--lang python,rust] [--limit N]

Every accepted training pair was verified under sitting_duck 1a10b7d with the
fix/127 selector macros. The engine has moved since (#137 rewired semantic type
codes). A label whose node set changed would teach a selector against an answer the
engine no longer gives, so this re-executes each pair's css on its fixture and
compares the digest with the frozen reference.sha256. Run it with the same
SITTING_DUCK / ASTCSS_MACROS the qualifier runs use.
"""
import argparse
import collections
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import verify as V  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", help="comma-separated languages (default: all)")
    ap.add_argument("--limit", type=int, default=0, help="first N pairs per language")
    args = ap.parse_args()
    want = set(args.lang.split(",")) if args.lang else None

    pairs, per_lang = [], collections.Counter()
    for path in sorted(glob.glob(os.path.join(HERE, "train/pairs/accepted-*.jsonl"))):
        for line in open(path):
            if not line.strip():
                continue
            p = json.loads(line)
            lang = p["id"].split("-")[1]
            if want and lang not in want:
                continue
            if args.limit and per_lang[lang] >= args.limit:
                continue
            per_lang[lang] += 1
            pairs.append(p)

    print("engine:", json.dumps(V.engine_identity()))
    got = V.execute([("q%d" % i, p["fixture"], p["css"]) for i, p in enumerate(pairs)])
    stats = collections.defaultdict(collections.Counter)
    for i, p in enumerate(pairs):
        lang = p["id"].split("-")[1]
        r = got["q%d" % i]
        if "error" in r:
            stats[lang]["error"] += 1
            print("ERROR   %-22s %-40s %s" % (p["id"], p["css"][:40], r["error"][:100]))
        elif V._digest(r["nodes"]) == p["reference"]["sha256"]:
            stats[lang]["same"] += 1
        else:
            stats[lang]["changed"] += 1
            print("CHANGED %-22s %-40s %d -> %d nodes" % (p["id"], p["css"][:40], p["reference"]["count"], len(r["nodes"])))
    print("\n%-12s %6s %8s %6s" % ("language", "same", "changed", "error"))
    for lang in sorted(stats):
        s = stats[lang]
        print("%-12s %6d %8d %6d" % (lang, s["same"], s["changed"], s["error"]))
    total = sum(stats.values(), collections.Counter())
    print("%-12s %6d %8d %6d" % ("total", total["same"], total["changed"], total["error"]))


if __name__ == "__main__":
    main()
