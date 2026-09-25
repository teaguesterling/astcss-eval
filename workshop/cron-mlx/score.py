"""Score predictions by WHAT THEY DO, not what they say.

    python3 score.py --pred preds.jsonl --ref data/eval.jsonl

preds.jsonl: one {"id": n, "prediction": "<cron>"} per line, in any order.
Reports execution match, string match, and the gap between them -- which is the point.
"""
import argparse, json, sys
from cron import equivalent, parse, CronError


def load_ref(path):
    out = []
    for i, line in enumerate(open(path)):
        ms = json.loads(line)["messages"]
        out.append({"id": i,
                    "request": next(m["content"] for m in ms if m["role"] == "user"),
                    "reference": next(m["content"] for m in ms if m["role"] == "assistant")})
    return out


def first_line(text):
    for raw in (text or "").strip().splitlines():
        s = raw.strip().strip("`").strip()
        if s:
            return s
    return ""


def score(refs, preds):
    t = {"n": 0, "exec": 0, "exact": 0, "parses": 0, "misses": []}
    by_id = {p["id"]: first_line(p.get("prediction", "")) for p in preds}
    for r in refs:
        got = by_id.get(r["id"], "")
        t["n"] += 1
        ok_parse = True
        try:
            parse(got)
        except CronError:
            ok_parse = False
        t["parses"] += 1 if ok_parse else 0
        ex = equivalent(got, r["reference"])
        t["exec"] += 1 if ex else 0
        t["exact"] += 1 if got == r["reference"] else 0
        if not ex:
            t["misses"].append((r["request"], r["reference"], got))
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pred", required=True)
    ap.add_argument("--ref", default="data/eval.jsonl")
    ap.add_argument("--show", type=int, default=8)
    a = ap.parse_args()
    refs = load_ref(a.ref)
    preds = [json.loads(l) for l in open(a.pred) if l.strip()]
    t = score(refs, preds)
    n = max(t["n"], 1)
    print("n=%d   parses %5.1f%%   EXECUTION %5.1f%%   string %5.1f%%"
          % (t["n"], 100 * t["parses"] / n, 100 * t["exec"] / n, 100 * t["exact"] / n))
    print("the gap between execution and string is the number of correct answers a "
          "string grader would have thrown away: %d" % (t["exec"] - t["exact"]))
    for req, want, got in t["misses"][:a.show]:
        print("  %-44s want %-20s got %r" % (req[:44], want, got))
    return 0


if __name__ == "__main__":
    sys.exit(main())
