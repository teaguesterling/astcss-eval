"""Which held pairs does the CURRENT engine now reproduce?

    python3 workspace/recover_pairs.py

Every pending pair carries an oracle-verified reference -- a node count and a sha256 of the
node list -- recorded when it was written. A pair is RECOVERABLE when today's engine returns
exactly that node set: same count, same digest. Anything else stays held, including a pair
that now returns a *different* non-empty answer, which is worse than an error because it
looks like success.

Also re-verifies the 55 pairs eval_t5 already uses. That is the gating question for moving
the engine pin: if the current engine reproduces all 55 unchanged, the pin can move and old
scores stay comparable. If it does not, growing the eval means re-baselining every model.
"""
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import verify as V  # noqa: E402

SOURCES = ["eval_t5/pairs/pending-t5-b1.jsonl",
           "workspace/siblings1/pairs/pending-siblings1.jsonl",
           "workspace/callgraph1/pairs/pending-callgraph1.jsonl"]
CURRENT = ["eval_t5/pairs/accepted-t5-b1.jsonl", "eval_t5/pairs/accepted-t5-b2.jsonl"]


def load(paths):
    out = []
    for p in paths:
        f = os.path.join(HERE, p)
        if not os.path.exists(f):
            continue
        for line in open(f):
            if line.strip():
                r = json.loads(line)
                r["_src"] = p.split("/")[1] if "/" in p else p
                out.append(r)
    return out


def check(rows, label):
    queries = [(r["id"], r["fixture"], r["css"]) for r in rows]
    got = V.execute(queries)
    tally = {"match": [], "differs": [], "error": [], "noref": []}
    for r in rows:
        ref = r.get("reference") or {}
        res = got.get(r["id"], {})
        if not ref.get("sha256"):
            tally["noref"].append(r); continue
        if "error" in res:
            tally["error"].append((r, res["error"])); continue
        d = V._digest(res["nodes"])
        if d == ref["sha256"] and len(res["nodes"]) == ref.get("count"):
            tally["match"].append(r)
        else:
            tally["differs"].append((r, len(res["nodes"]), ref.get("count")))
    print("%s: %d pairs -> %d reproduce, %d differ, %d error, %d had no reference"
          % (label, len(rows), len(tally["match"]), len(tally["differs"]),
             len(tally["error"]), len(tally["noref"])))
    return tally


def main():
    print("engine macros: %s\n" % V.MACROS)
    cur = check(load(CURRENT), "eval_t5 AS IT STANDS")
    if cur["differs"] or cur["error"]:
        print("  !! the pin CANNOT move without re-baselining; offenders:")
        for r, n, want in cur["differs"][:6]:
            print("     %-10s %-44s now %s, was %s" % (r["id"], r["css"][:44], n, want))
        for r, e in cur["error"][:6]:
            print("     %-10s %-44s %s" % (r["id"], r["css"][:44], str(e)[:50]))
    print()

    held = load(SOURCES)
    t = check(held, "HELD PAIRS")
    import collections
    by_tag = collections.Counter()
    for r in t["match"]:
        for tag in (r.get("tags") or ["(untagged)"]):
            by_tag[tag] += 1
    print("\nRECOVERABLE, by the defect they were held on:")
    for tag, n in by_tag.most_common():
        print("  %-42s %3d" % (tag, n))
    still = collections.Counter()
    for r, *_ in t["differs"] + t["error"]:
        for tag in (r.get("tags") or ["(untagged)"]):
            still[tag] += 1
    print("\nSTILL HELD:")
    for tag, n in still.most_common():
        print("  %-42s %3d" % (tag, n))

    out = os.path.join(HERE, "workspace/recovered.jsonl")
    with open(out, "w") as fh:
        for r in t["match"]:
            r.pop("_src", None)
            fh.write(json.dumps(r) + "\n")
    print("\nwrote %d recoverable pairs -> %s" % (len(t["match"]), out))


if __name__ == "__main__":
    main()
