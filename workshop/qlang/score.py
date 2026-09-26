"""Score query predictions by execution, and per clause.

    python3 score.py --pred preds.jsonl --ref data/eval.jsonl

Four numbers that a single score would hide:

  json      did it emit a parseable object at all
  runs      does that object execute against the table
  EXEC      does it return the same rows, in the same order, as the reference
  string    is it byte-identical to the reference

plus one column per clause -- where / order_by / limit / select -- because the point of a
nested target is that the parts fail separately. A model that filters correctly and orders
wrongly tells you where to spend the next hour; "41%" does not.

Clause scoring is BEHAVIOURAL where it can be. A `where` clause counts as right when it
selects the same rows as the reference's `where`, so {"price": {"gt": 10}} and
{"price": {"gte": 11}} are the same filter on integer prices. Only `select` and `limit`,
which have no behaviour apart from their value, compare literally.
"""
import argparse
import json
import sys

from qlang import run, parse, QueryError, TABLE

CLAUSES = ("where", "order_by", "limit", "select")


def clause_ok(name, got, want):
    """Did this clause do the same thing? Behaviourally for `where`, literally otherwise."""
    if (name in got) != (name in want):
        return False
    if name not in want:
        return True                                  # both absent: agreed
    if name != "where":
        return got[name] == want[name]
    try:                                             # same filter = same surviving rows
        a = run({"where": got["where"]})
        b = run({"where": want["where"]})
    except (QueryError, TypeError):
        return False
    return a == b


def load_ref(path):
    out = []
    for i, line in enumerate(open(path)):
        ms = json.loads(line)["messages"]
        out.append({"id": i,
                    "request": next(m["content"] for m in ms if m["role"] == "user"),
                    "reference": next(m["content"] for m in ms if m["role"] == "assistant")})
    return out


def score(refs, preds):
    by_id = {p["id"]: p.get("prediction", "") for p in preds}
    t = {k: 0 for k in ("n", "json", "runs", "exec", "string") + CLAUSES}
    misses = []
    for r in refs:
        raw = by_id.get(r["id"], "")
        want = json.loads(r["reference"])
        got = parse(raw)
        t["n"] += 1
        t["string"] += 1 if raw.strip() == r["reference"] else 0
        if got is None:
            misses.append((r["request"], r["reference"], raw.strip()[:60], "no json"))
            continue
        t["json"] += 1
        for c in CLAUSES:
            t[c] += 1 if clause_ok(c, got, want) else 0
        try:
            rows = run(got)
        except (QueryError, TypeError) as e:
            misses.append((r["request"], r["reference"], json.dumps(got), str(e)[:40]))
            continue
        t["runs"] += 1
        if rows == run(want):
            t["exec"] += 1
        else:
            misses.append((r["request"], r["reference"], json.dumps(got), "wrong rows"))
    return t, misses


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True)
    ap.add_argument("--ref", default="data/eval.jsonl")
    ap.add_argument("--show", type=int, default=6)
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    refs = load_ref(a.ref)
    preds = [json.loads(l) for l in open(a.pred) if l.strip()]
    t, misses = score(refs, preds)
    n = max(t["n"], 1)
    pct = lambda k: 100.0 * t[k] / n
    print("%-22s n=%-4d json %5.1f%%  runs %5.1f%%  EXEC %5.1f%%  string %5.1f%%   "
          "| where %5.1f%%  order %5.1f%%  limit %5.1f%%  select %5.1f%%"
          % (a.label or a.pred, t["n"], pct("json"), pct("runs"), pct("exec"), pct("string"),
             pct("where"), pct("order_by"), pct("limit"), pct("select")))
    for req, want, got, why in misses[:a.show]:
        print("   %-46s %-12s want %s" % (req[:46], why, want))
        print("   %-46s              got  %s" % ("", got))
    return 0


if __name__ == "__main__":
    sys.exit(main())
