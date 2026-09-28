"""Verify the unused tier-5 candidates, so eval_t5 can grow past its 1.8-point quantum.

    python3 workspace/verify_t5_b3.py

eval_t5 is 55 pairs. One pair on it is 1.8 points, and a five-seed replicate puts the
seed noise at 7.3 points -- so the eval cannot currently see anything smaller than four
pairs of difference, which is most of what is left to measure.

`eval_t5/candidates/selectors.jsonl` holds 126 candidates; 55 became pairs. Of the rest,
79 are clean: never used in the eval, and their selector never appears as a training
answer in workspace/datasets/t5-langcard. This verifies those 79 the same way the
existing 42 accepted pairs were verified -- reference executes, node count in bounds,
and NOT vacuous against its own relaxations and distractors.

PINNED ENGINE on purpose. The 42 accepted pairs carry engine-sourced references recorded
on sd-20260914-1835, and the current sitting_duck main disagrees with at least one of them
(t5-p55, ::callees: 5 nodes then, 1 now). Verifying new pairs on a different engine than
the old ones would put two incompatible references in one eval.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import qualify as Q  # noqa: E402
import verify as V   # noqa: E402


def main():
    Q.PAIRS_DIR = "eval_t5"
    used = {p["css"].strip() for p in Q.load_pairs()}
    train = set()
    for line in open(os.path.join(HERE, "workspace/datasets/t5-langcard/train.jsonl")):
        train.add(next(m["content"] for m in json.loads(line)["messages"]
                       if m["role"] == "assistant").strip())

    cands = [json.loads(l) for l in
             open(os.path.join(HERE, "eval_t5/candidates/selectors.jsonl"))]
    clean = [c for c in cands
             if c["css"].strip() not in used and c["css"].strip() not in train]
    print("engine : %s" % V.MACROS.split("/")[-1])
    print("candidates %d, already used %d, leak into training %d, CLEAN %d"
          % (len(cands), len(cands) - len([c for c in cands if c["css"].strip() not in used]),
             len([c for c in cands if c["css"].strip() in train]), len(clean)))

    pairs = [{"id": c["id"], "fixture": c["fixture"], "selector": c["css"],
              "distractors": c.get("distractors") or []} for c in clean]
    rep = V.verify(pairs)

    ok, bad = [], []
    for c in clean:
        r = rep[c["id"]]
        (ok if r["ok"] else bad).append((c, r))
    print("\nVERIFIED %d of %d" % (len(ok), len(clean)))

    import collections
    why = collections.Counter()
    for c, r in bad:
        why[(r["reasons"] or ["(none)"])[0].split(" ->")[0][:52]] += 1
    print("\nrejected, by first reason:")
    for k, n in why.most_common():
        print("  %-54s %3d" % (k, n))

    out = os.path.join(HERE, "workspace/t5-b3-verified.jsonl")
    with open(out, "w") as fh:
        for c, r in ok:
            fh.write(json.dumps({"id": c["id"], "tier": "5", "fixture": c["fixture"],
                                 "css": c["css"], "gloss": c["gloss"],
                                 "distractors": c.get("distractors") or [],
                                 "struct": c.get("struct"),
                                 "reference": {k: v for k, v in r["reference"].items()
                                               if k != "nodes"} | {"source": "engine"},
                                 "verification": {"batch": "t5-b3", "method": "engine",
                                                  "engine": "pinned sd-20260914-1835"}}) + "\n")
    print("\nwrote %d verified candidates -> %s" % (len(ok), out))
    print("they still need an `nl` written before they are pairs.")


if __name__ == "__main__":
    main()
