"""Declare the MINED near-miss as a distractor on every pseudo-form eval_t5 pair, and let the
engine say which pairs cannot withhold credit from it.

This is an instrument check, not a change: it runs the same gate that training batches pass
(verify.py: a distractor that returns the reference's node set REJECTS the pair) over pairs
that are already in the eval. t5-p55 is the known case. The mined set says there are ~24.

The near-miss per form is not invented -- it is what the seven rebase120 models actually
answered and were given credit for:

    ::callees      -> .fn#X .call              :called-by(X) -> .fn#X .call
    ::callers      -> .fn:has(.call#X)         :calls(X)     -> .fn:has(.call#X)
    :is-called     -> :has(.call)              :scope(X)     -> descendant, :in-scope(X)
"""
import json, os, re, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")
import verify as V

def near_misses(css):
    """The syntactic lookalikes a model reaches for. Empty when the form has none."""
    out = []
    m = re.match(r'^\.fn#([\w$]+)::callees$', css)
    if m: out.append(".fn#%s .call" % m.group(1))
    m = re.match(r'^\.fn#([\w$]+)::callers$', css)
    if m: out.append(".fn:has(.call#%s)" % m.group(1))
    m = re.match(r'^\.call:called-by\(([\w$]+)\)$', css)
    if m: out.append(".fn#%s .call" % m.group(1))
    for m in re.finditer(r':calls\(([\w$]+)\)', css):
        out.append(css.replace(":calls(%s)" % m.group(1), ":has(.call#%s)" % m.group(1)))
    if ':is-called' in css:
        out.append(css.replace(":is-called", ":has(.call)"))
    m = re.match(r'^(\.\w+):scope\((\.\w+#[\w$]+)\)$', css)
    if m:
        out.append("%s %s" % (m.group(2), m.group(1)))            # descendant
        out.append("%s:in-scope(%s)" % (m.group(1), m.group(2)))  # the other scope form
    return [o for o in dict.fromkeys(out) if o != css]

rows = []
for f in sorted(__import__("glob").glob("eval_t5/pairs/accepted-*.jsonl") +
                __import__("glob").glob("eval_t5/pairs/pending-*.jsonl")):
    for l in open(f):
        if l.strip():
            r = json.loads(l); r["_file"] = f; rows.append(r)

todo = [(r, near_misses(r["css"])) for r in rows]
todo = [(r, nm) for r, nm in todo if nm]
print("pairs with a mineable near-miss: %d of %d" % (len(todo), len(rows)), file=sys.stderr)

rep = V.verify([{"id": r["id"], "fixture": r["fixture"], "selector": r["css"],
                 "distractors": nm} for r, nm in todo])

ties, clean = [], []
for r, nm in todo:
    e = rep[r["id"]]
    tied = [d["selector"] for d in e["distractors"] if "matches the reference" in d["verdict"]]
    (ties if tied else clean).append((r, tied, e))

print("\n%-9s %-44s %s" % ("id", "reference", "verdict"))
for r, tied, e in sorted(ties, key=lambda t: t[0]["id"]):
    print("%-9s %-44s TIES %s" % (r["id"], r["css"], ", ".join(tied)))
print("\n--- discriminates (the near-miss returns a different set) ---")
for r, _, e in sorted(clean, key=lambda t: t[0]["id"]):
    d = "; ".join("%s %s" % (x["selector"], x["verdict"]) for x in e["distractors"])
    print("%-9s %-44s %s" % (r["id"], r["css"], d[:60]))

json.dump({"ties": [r["id"] for r, _, _ in ties],
           "clean": [r["id"] for r, _, _ in clean],
           "detail": {r["id"]: {"css": r["css"], "fixture": r["fixture"], "tied_with": t}
                      for r, t, _ in ties}},
          open("workspace/eval_pseudo_audit.json", "w"), indent=1)
print("\n=== %d of %d probed pairs cannot withhold credit from the near-miss ===" % (len(ties), len(todo)))
