"""Rescore surface-study rows, scoring the SELECTOR part by execution.

    python3 surface/score.py workspace/surface/rows-smoke1.jsonl

Why not string equality: for "drop the print call inside bulk_import" the reference is
`.fn#bulk_import .call#print`, but `.call#print` selects the SAME single node in this
fixture and is an equally correct answer. This project scores selectors by execution
everywhere else -- the eval's whole premise -- so scoring them by string here would invent
failures and, worse, would flatter whichever surface happens to elicit verbose selectors.
`.print` still scores wrong: it matches nothing.

Generation and scoring are separate so rows can be rescored without re-querying any model.

Reported per arm:
  parse buckets   ok / wrong_surface / malformed / error
  parts           selector (by execution) / op / args, each independently
  all             all three parts right
  arity-0 subset  the only tasks whose argument is not partly transcribed from the request,
                  so the cleanest signal available here
"""
import collections
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "surface"))

import verify                      # noqa: E402
import surfaces as S               # noqa: E402

FIXTURE_KEY = "surface-sample"


def node_sets(selectors, fixture_rel):
    """Execute every distinct selector once; unparseable/refused ones map to None."""
    verify.FIXTURES[FIXTURE_KEY] = fixture_rel
    qs, out = [], {}
    uniq = sorted({s for s in selectors if s})
    for i, sel in enumerate(uniq):
        qs.append(("S%d" % i, FIXTURE_KEY, sel))
    if not qs:
        return out
    res = verify.execute(qs)
    for i, sel in enumerate(uniq):
        r = res.get("S%d" % i, {})
        out[sel] = None if "error" in r else frozenset(r["nodes"])
    return out


def main(argv=None):
    paths = (argv or sys.argv[1:]) or []
    if not paths:
        sys.exit(__doc__.strip().splitlines()[2].strip())
    spec = json.load(open(os.path.join(HERE, "surface", "tasks.json")))
    tasks = {t["id"]: t for t in spec["tasks"]}

    rows = []
    for p in paths:
        path = p if os.path.isabs(p) else os.path.join(HERE, p)
        rows += [json.loads(l) for l in open(path) if l.strip()]

    wanted = [t["selector"] for t in spec["tasks"]]
    got = [r["parsed"]["selector"] for r in rows if r.get("parsed")]
    sets = node_sets(wanted + got, spec["fixture"])

    arms = collections.OrderedDict()
    for r in rows:
        key = (r["model"], r["condition"], r["surface"])
        a = arms.setdefault(key, collections.Counter())
        a["n"] += 1
        a[r["status"]] += 1
        t = tasks[r["task"]]
        # Count the arity-0 DENOMINATOR before bailing out on unparsed rows: tallying it
        # after the `continue` hid every malformed answer, so a surface that failed all its
        # arity-0 tasks reported 0/0 -- as if it had never been asked one -- which flatters
        # precisely the surfaces that parse worst.
        if t["arity"] == 0:
            a["n0"] += 1
        parsed = r.get("parsed")
        if not parsed:
            continue
        ref, mine = sets.get(t["selector"]), sets.get(parsed["selector"])
        sel_ok = ref is not None and mine is not None and ref == mine
        norm = (lambda s: " ".join(str(s).split()).strip("'\""))
        op_ok = norm(parsed["op"]) == norm(t["op"])
        args_ok = [norm(x) for x in parsed["args"]] == [norm(x) for x in t["args"]]
        a["selector"] += sel_ok
        a["op"] += op_ok
        a["args"] += args_ok
        a["all"] += sel_ok and op_ok and args_ok
        if t["arity"] == 0:
            a["all0"] += sel_ok and op_ok and args_ok

    hdr = ("%-34s %-11s %4s | %3s %3s %3s %3s | %4s %4s %4s %4s | %s"
           % ("model", "surface", "n", "ok", "ws", "mal", "err",
              "sel", "op", "args", "ALL", "arity0"))
    print(hdr)
    print("-" * len(hdr))
    for (model, cond, surf), a in sorted(arms.items(), key=lambda kv: (kv[0][0], kv[0][2])):
        print("%-34s %-11s %4d | %3d %3d %3d %3d | %4d %4d %4d %4d | %d/%d"
              % (model.split("/")[-1] + ("" if cond == "card" else "/" + cond),
                 surf, a["n"], a["ok"], a["wrong_surface"], a["malformed"], a["error"],
                 a["selector"], a["op"], a["args"], a["all"], a["all0"], a["n0"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
