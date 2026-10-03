"""Per-family and per-language scores on the holdout suite, with counts beside percentages.

Counts matter here: ho-go-nghttp2 is 2 files and ho-bash-plinking has 3 `.fn`, so those
languages carry few questions and a percentage alone would overstate what is known.
"""
import json, glob, os, collections, sys
pairs = {}
for f in glob.glob("holdout/pairs/accepted-*.jsonl"):
    for l in open(f):
        if l.strip():
            r = json.loads(l); pairs[r["id"]] = r
runs = sorted(glob.glob("runs/ho-*/scores.jsonl"))
if not runs:
    sys.exit("no scored holdout runs yet")
print("%-18s %6s %7s %7s" % ("model", "n", "exec", "match"))
rowsets = {}
for p in runs:
    tag = p.split("/")[1][3:]
    rows = [json.loads(l) for l in open(p)]
    rowsets[tag] = rows
    n = len(rows)
    print("%-18s %6d %6.1f%% %6.1f%%" % (tag, n,
          100.0*sum(bool(r.get("executes")) for r in rows)/max(n,1),
          100.0*sum(bool(r.get("exec_match")) for r in rows)/max(n,1)))
for key, label in (("family", "FAMILY"), ("lang", "LANGUAGE")):
    groups = sorted({pairs[r["id"]][key] for rows in rowsets.values() for r in rows if r["id"] in pairs})
    print("\n=== by %s (n in parens) ===" % label)
    print("%-18s %s" % ("model", " ".join("%-14s" % g[:14] for g in groups)))
    for tag, rows in rowsets.items():
        cells = []
        for g in groups:
            sub = [r for r in rows if r["id"] in pairs and pairs[r["id"]][key] == g]
            cells.append("%-14s" % ("-" if not sub else "%.0f%% (%d)" % (
                100.0*sum(bool(r.get("exec_match")) for r in sub)/len(sub), len(sub))))
        print("%-18s %s" % (tag, " ".join(cells)))
