"""What is actually in each holdout fixture? Node counts for the card's vocabulary, so the
question writer targets constructs that exist and references that land in verify's 1..50.

Also the first check that the engine can parse these repos at all -- two languages here
(typescript, ruby) have never been exercised by this project.
"""
import json, os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import verify as V

FX = sorted(json.load(open("holdout/fixtures/MANIFEST.json"))["fixtures"])
CLASSES = [".fn", ".class", ".call", ".loop", ".if", ".try", ".catch", ".var", ".import",
           ".member", ".jump", ".throw", ".comp", ".mod", ".str", ".param"]
q = [("%s|%s" % (fx, c), fx, c) for fx in FX for c in CLASSES]
got = V.execute(q)
n = lambda fx, c: (-1 if "error" in got.get("%s|%s" % (fx, c), {"error": 1})
                   else len(got["%s|%s" % (fx, c)]["nodes"]))
print("%-22s %s" % ("fixture", " ".join("%-7s" % c for c in CLASSES)))
counts = {}
for fx in FX:
    row = []
    for c in CLASSES:
        v = n(fx, c); counts["%s|%s" % (fx, c)] = v
        row.append("%-7s" % ("ERR" if v < 0 else v))
    print("%-22s %s" % (fx, " ".join(row)))
json.dump(counts, open("workspace/holdout_counts.json", "w"), indent=1)
dead = [fx for fx in FX if n(fx, ".fn") <= 0]
print("\nfixtures with no .fn (engine cannot see them): %s" % (dead or "none"))
