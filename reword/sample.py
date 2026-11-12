"""Draw a representative sample of NL queries to probe each generator's register.

The point is NOT to produce training data yet. It is to find out, cheaply, whether nine
models actually write in nine registers or in one. The 4B arm failed because a single
generator wiped out the interrogative register (45.5% of human paraphrases end in '?'
against 0.1% of the 4B's) and cost 12 points on the reworded holdout. Nine models that all
write fluent declaratives would reproduce that at nine times the cost.

Sampled across all three populations we would ever reword, because they differ in register
already: eval_t5 (tier-5 compound selectors, authored with the corpus), the holdout (terse and
imperative, hand-written), and the training corpus itself.
"""
import json, glob, random, os, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rnd = random.Random("reword-sample-v1")

def take(paths, n, tag):
    rows = []
    for p in paths:
        for l in open(p):
            if l.strip():
                r = json.loads(l)
                if r.get("nl") and r.get("css"):
                    rows.append({"id": r["id"], "nl": r["nl"], "css": r["css"], "pop": tag})
    rnd.shuffle(rows)
    return rows[:n]

sample = (take(sorted(glob.glob("eval_t5/pairs/accepted-*.jsonl")), 40, "eval_t5")
        + take(sorted(glob.glob("holdout/pairs/accepted-*.jsonl")), 40, "holdout")
        + take(["workspace/trainset-t5/pairs.jsonl"], 40, "corpus"))
with open("reword/sample.jsonl", "w") as fh:
    for r in sample: fh.write(json.dumps(r) + "\n")
import collections
print("%d queries -> reword/sample.jsonl  %s" % (len(sample), dict(collections.Counter(r["pop"] for r in sample))))
for r in sample[:4]: print("   %-10s %s" % (r["pop"], r["nl"][:62]))
