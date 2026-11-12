"""Do the ORACLE-sourced eval_t5 references agree with the pinned engine?

13 of the 118 eval_t5 pairs carry reference.source == "oracle", and qualify.score branches on
that: those pairs are scored against oracle.py's Python model of the semantics, not against
the engine every other pair is scored against. Two instruments in one eval.

That already produced a visible disagreement. On t5-p43 the engine says
`.call:scope(.fn#load)` and `.fn#load .call` return DIFFERENT node sets, while six models
answered the descendant form and were CREDITED -- because the oracle equates them.

This runs each oracle-sourced reference through the engine and compares node sets with the
stored digest. Three outcomes:
  AGREE      engine and oracle pick the same nodes -> the pair can simply be re-sourced to
             the engine and the dual-instrument problem goes away for it
  DISAGREE   they pick different nodes -> the pair is measuring oracle.py, and its verdicts on
             real models are not comparable with the other 105 pairs
  ERROR      the engine refuses the reference -> the selector is not executable at all
"""
import glob, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
import verify as V

rows = []
for f in sorted(glob.glob("eval_t5/pairs/accepted-*.jsonl") + glob.glob("eval_t5/pairs/pending-*.jsonl")):
    for l in open(f):
        if l.strip():
            r = json.loads(l)
            if (r.get("reference") or {}).get("source") == "oracle":
                r["_file"] = os.path.basename(f); rows.append(r)
print("oracle-sourced pairs: %d" % len(rows), file=sys.stderr)
got = V.execute([(r["id"], r["fixture"], r["css"]) for r in rows])

out = {"agree": [], "disagree": [], "error": []}
print("%-9s %-44s %-8s %-8s %s" % ("id", "reference", "oracle", "engine", "verdict"))
for r in rows:
    g = got[r["id"]]
    stored = r["reference"]
    if "error" in g:
        v, eng = "ERROR", "-"
        out["error"].append(r["id"])
    else:
        eng = len(g["nodes"])
        same = V._digest(g["nodes"]) == stored.get("sha256")
        v = "AGREE" if same else "DISAGREE"
        out["agree" if same else "disagree"].append(r["id"])
    print("%-9s %-44s %-8s %-8s %s" % (r["id"], r["css"][:44], stored.get("count"), eng, v))
json.dump(out, open("workspace/oracle_adjudication.json", "w"), indent=1)
print("\nagree %d, disagree %d, error %d" % (len(out["agree"]), len(out["disagree"]), len(out["error"])))
print("\nDISAGREE pairs are scored by a different instrument than the other 105:")
for pid in out["disagree"]:
    r = next(x for x in rows if x["id"] == pid)
    print("   %-9s %-42s nl=%s" % (pid, r["css"][:42], r["nl"][:46]))
