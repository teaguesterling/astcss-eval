"""Gate the holdout candidates through the engine, exactly as a training batch is gated.

Same verify.py: the reference must execute and land in 1..50 nodes, and every modifier must be
load-bearing (a `:not(...)` that changes nothing is a question with a misleading answer). No
distractors here -- this suite measures general accuracy, not one confusion.
"""
import json, os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import verify as V

CAND = "holdout/pairs/candidates.jsonl"
rows = [json.loads(l) for l in open(CAND) if l.strip()]
ident = V.engine_identity()
rep = V.verify([{"id": r["id"], "fixture": r["fixture"], "selector": r["css"]} for r in rows])
acc, why = [], collections.Counter()
for r in rows:
    e = rep[r["id"]]
    if e["ok"]:
        r["reference"] = e["reference"]
        r["verification"] = {"batch": "holdout-v1", "engine": ident,
                             "relaxations": e["relaxations"]}
        acc.append(r)
    else:
        for reason in e["reasons"]:
            why["bounds" if "need" in reason else
                "vacuous" if "load-bearing" in reason else
                "errors" if "error" in reason else reason[:30]] += 1
with open("holdout/pairs/accepted-holdout.jsonl", "w") as fh:
    for r in acc: fh.write(json.dumps(r) + "\n")
print("candidates %d -> ACCEPTED %d" % (len(rows), len(acc)))
print("rejections: %s" % dict(why))
print("accepted by family:   %s" % dict(collections.Counter(r["family"] for r in acc)))
print("accepted by language: %s" % dict(collections.Counter(r["lang"] for r in acc)))
