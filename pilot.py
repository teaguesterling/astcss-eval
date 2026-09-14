"""Verify a batch of candidate pairs and split it into accepted and rejected.

usage: pilot.py <candidates.jsonl> <batch-id>

Writes, under this directory:
  pairs/accepted-<batch>.jsonl   rows that passed every gate, in SCHEMA.md shape
  pairs/rejected-<batch>.jsonl   rows that failed, with every reason
  batches/<batch>.json           engine identity, timestamp, and counts

Gates, cheapest first. The static ones are rules from SPEC.md §5 that no engine
can check; the rest come from verify.py:
  - the NL contains no selector syntax
  - at least two paraphrases, and no two of nl+paraphrases share more than
    half their content words
  - at least two distractors
  - verify.verify(): bounds, load-bearing modifiers, distractors differ
  - no two accepted pairs on the same fixture freeze the same node set
"""
import json
import os
import re
import sys
import time

import verify as V

HERE = os.path.dirname(os.path.abspath(__file__))

STOP = set("""a an the of in to for and or with that which is are be all any every each
what who show list find me my our their there this those these do does did from by on at
as into it its i we you your can get gets here where when how""".split())
SELECTOR_SYNTAX = re.compile(r"[#\[\]{}()>~+:]|(?<![a-z])\.[a-z_]")


def content_words(text):
    return {w for w in re.findall(r"[a-z0-9_]+", text.lower()) if w not in STOP}


def static_reasons(p):
    reasons = []
    if SELECTOR_SYNTAX.search(p.get("nl", "")):
        reasons.append("nl contains selector syntax")
    paras = p.get("paraphrases", [])
    if len(paras) < 2:
        reasons.append("fewer than 2 paraphrases")
    texts = [p.get("nl", "")] + paras
    for i in range(len(texts)):
        if i and SELECTOR_SYNTAX.search(texts[i]):
            reasons.append("paraphrase %d contains selector syntax" % i)
        for j in range(i + 1, len(texts)):
            a, b = content_words(texts[i]), content_words(texts[j])
            shared = a & b
            if a and b and len(shared) > min(len(a), len(b)) / 2:
                reasons.append("texts %d and %d share more than half their content words (%s)"
                               % (i, j, ", ".join(sorted(shared))))
    if len(p.get("distractors", [])) < 2:
        reasons.append("fewer than 2 distractors")
    if p.get("fixture") not in V.FIXTURES:
        reasons.append("unknown fixture %r" % p.get("fixture"))
    return reasons


def main(path, batch):
    rows = [json.loads(line) for line in open(path) if line.strip()]
    for r in rows:
        r["selector"] = r["css"]
    report = V.verify(rows)
    engine = V.engine_identity()

    accepted, rejected, seen = [], [], {}
    for r in rows:
        v = report[r["id"]]
        reasons = static_reasons(r) + list(v["reasons"])
        ref = v.get("reference")
        if ref and not reasons:
            key = (r["fixture"], ref["sha256"])
            if key in seen:
                reasons.append("same node set as %s on %s" % (seen[key], r["fixture"]))
            else:
                seen[key] = r["id"]
        out = {k: r[k] for k in ("id", "tier", "nl", "paraphrases", "css", "fixture", "distractors")}
        out["treeql"] = r.get("treeql")
        out["verification"] = {"batch": batch, "relaxations": v["relaxations"], "distractors": v["distractors"]}
        if reasons:
            out["tags"] = ["rejected"]
            out["reasons"] = reasons
            if ref:
                out["reference"] = ref
            rejected.append(out)
        else:
            out["tags"] = ["sitting_duck_supported", "v0"]
            out["reference"] = ref
            accepted.append(out)

    os.makedirs(os.path.join(HERE, "pairs"), exist_ok=True)
    os.makedirs(os.path.join(HERE, "batches"), exist_ok=True)
    for name, data in (("accepted", accepted), ("rejected", rejected)):
        with open(os.path.join(HERE, "pairs", "%s-%s.jsonl" % (name, batch)), "w") as fh:
            for row in data:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    by_tier = {}
    for row in accepted:
        by_tier[row["tier"]] = by_tier.get(row["tier"], 0) + 1
    meta = {"batch": batch, "source": os.path.relpath(path, HERE),
            "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "engine": engine,
            "candidates": len(rows), "accepted": len(accepted), "rejected": len(rejected),
            "accepted_by_tier": by_tier}
    with open(os.path.join(HERE, "batches", "%s.json" % batch), "w") as fh:
        json.dump(meta, fh, indent=2, sort_keys=True)

    print("batch %s: %d candidates, %d accepted %s, %d rejected\n"
          % (batch, len(rows), len(accepted), by_tier, len(rejected)))
    for row in accepted + rejected:
        ok = "ACCEPT" if row in accepted else "reject"
        n = row.get("reference", {}).get("count", "-")
        print("%-6s %-7s %-44s %-13s n=%s" % (ok, row["id"], row["css"][:44], row["fixture"], n))
        for why in row.get("reasons", []):
            print("         - %s" % why)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
