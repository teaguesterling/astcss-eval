"""Verify a batch of candidate pairs and split it into accepted and rejected.

usage: pilot.py <candidates.jsonl> <batch-id> [root]

`root` (default: this directory) holds pairs/ and batches/; training batches use
`train`, so they never write into, or deduplicate against, the eval's pairs/.

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
import glob
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


HAS_RE = re.compile(r"^(?P<outer>.+?)(?P<neg>:not\(:has\(|:has\()(?P<inner>[^()]+)\)\)?$")


def has_truth_mismatches(rows):
    """Training gate: a :has / :not(:has) selector must select exactly the outer nodes
    that do (not) contain a node its inner selector matches on its own.

    Inside :has the engine also counts syntax-only keyword tokens (sitting_duck #133):
    every Python function "contains a function" through its own `def`, and the
    training-fixture audit showed the same leak in Rust, JavaScript and Go. A pair
    verified against that node set would pass gates it shouldn't."""
    checks = []
    for r in rows:
        m = HAS_RE.match(r.get("css", ""))
        if m and r.get("fixture") in V.FIXTURES:
            checks.append((r["id"], r["fixture"], m.group("outer"), m.group("neg").startswith(":not"),
                           m.group("inner"), r["css"]))
    if not checks:
        return {}
    lines = []
    for fx in sorted({c[1] for c in checks}):
        lines.append("CREATE TABLE %s AS SELECT * FROM read_ast('%s');"
                     % (V._table(fx), V._q(os.path.join(V.HERE, V.FIXTURES[fx]))))
    for pid, fx, outer, neg, inner, css in checks:
        t = V._table(fx)
        lines.append("SELECT '@@BEGIN %s';" % pid)
        lines.append(
            "WITH o AS (SELECT s.file_path, s.node_id, x.descendant_count FROM ast_select_from('{t}', '{o}') s "
            "JOIN {t} x ON x.file_path = s.file_path AND x.node_id = s.node_id), "
            "i AS (SELECT file_path, node_id FROM ast_select_from('{t}', '{i}')), "
            "truth AS (SELECT o.file_path, o.node_id FROM o WHERE {neg} EXISTS (SELECT 1 FROM i "
            "WHERE i.file_path = o.file_path AND i.node_id > o.node_id AND i.node_id <= o.node_id + o.descendant_count)), "
            "eng AS (SELECT file_path, node_id FROM ast_select_from('{t}', '{s}')) "
            "SELECT '@@ROWS ' || (SELECT count(*) FROM truth) || ',' || (SELECT count(*) FROM eng) || ',' || "
            "(SELECT count(*) FROM (SELECT * FROM truth EXCEPT SELECT * FROM eng)) || ',' || "
            "(SELECT count(*) FROM (SELECT * FROM eng EXCEPT SELECT * FROM truth));"
            .format(t=t, o=V._q(outer), i=V._q(inner), s=V._q(css), neg="NOT" if neg else ""))
    got = V._collect(V._run_script(lines), "@@ROWS")
    bad = {}
    for pid, *_ in checks:
        g = got.get(pid, {})
        if "error" in g or "payload" not in g:
            continue  # verify() reports execution errors itself
        truth, eng, missing, extra = (int(x) for x in g["payload"].split(","))
        if missing or extra:
            bad[pid] = ("the engine's :has result disagrees with ground truth (%d truth, %d engine: "
                        "keyword-token leak, sitting_duck #133)" % (truth, eng))
    return bad


def main(path, batch, root=HERE):
    rows = [json.loads(line) for line in open(path) if line.strip()]
    for r in rows:
        r["selector"] = r["css"]
    report = V.verify(rows)
    # Training batches only: the eval's pairs were audited by hand (FINDINGS.md).
    has_bad = has_truth_mismatches(rows) if os.path.abspath(root) != HERE else {}
    engine = V.engine_identity()

    accepted, rejected, held, seen, prior_ids = [], [], [], {}, {}
    # Earlier batches' frozen pairs: a node set or id already taken is taken forever.
    for prior in sorted(glob.glob(os.path.join(root, "pairs", "*.jsonl"))):
        name = os.path.basename(prior)
        if name.startswith("rejected-") or name.endswith("-%s.jsonl" % batch):
            continue
        for line in open(prior):
            p = json.loads(line)
            prior_ids[p["id"]] = name
            if name == "retired.jsonl":
                # A retired id is never reused, but its node set is free again.
                continue
            seen[(p["fixture"], p["reference"]["sha256"])] = p["id"]
    for r in rows:
        v = report[r["id"]]
        reasons = static_reasons(r) + list(v["reasons"])
        if r["id"] in has_bad:
            reasons.append(has_bad[r["id"]])
        if r["id"] in prior_ids:
            reasons.append("id already frozen in %s" % prior_ids[r["id"]])
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
        pending = [t for t in r.get("tags", []) if t.startswith("pending_engine:")]
        if pending and not reasons:
            # It passes the gates, but the engine's answer is known wrong: keep the
            # frozen set for when the engine is fixed, never score it.
            out["tags"] = pending
            out["reference"] = ref
            held.append(out)
        elif reasons:
            out["tags"] = ["rejected"]
            out["reasons"] = reasons
            if ref:
                out["reference"] = ref
            rejected.append(out)
        else:
            out["tags"] = ["sitting_duck_supported", "v0"]
            out["reference"] = ref
            accepted.append(out)

    os.makedirs(os.path.join(root, "pairs"), exist_ok=True)
    os.makedirs(os.path.join(root, "batches"), exist_ok=True)
    for name, data in (("accepted", accepted), ("rejected", rejected), ("pending", held)):
        # Write-then-rename: several drafting agents verify concurrently and each reads
        # every other batch's pairs for duplicates, so no reader may see a partial file.
        dest = os.path.join(root, "pairs", "%s-%s.jsonl" % (name, batch))
        with open(dest + ".tmp", "w") as fh:
            for row in data:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        os.replace(dest + ".tmp", dest)
    by_tier = {}
    for row in accepted:
        by_tier[row["tier"]] = by_tier.get(row["tier"], 0) + 1
    meta = {"batch": batch, "source": os.path.relpath(path, HERE),
            "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "engine": engine,
            "candidates": len(rows), "accepted": len(accepted), "rejected": len(rejected),
            "pending": len(held), "accepted_by_tier": by_tier}
    dest = os.path.join(root, "batches", "%s.json" % batch)
    with open(dest + ".tmp", "w") as fh:
        json.dump(meta, fh, indent=2, sort_keys=True)
    os.replace(dest + ".tmp", dest)

    print("batch %s: %d candidates, %d accepted %s, %d pending, %d rejected\n"
          % (batch, len(rows), len(accepted), by_tier, len(held), len(rejected)))
    for row in accepted + held + rejected:
        ok = "ACCEPT" if row in accepted else ("hold" if row in held else "reject")
        if row in held:
            row = dict(row, reasons=row["tags"])
        n = row.get("reference", {}).get("count", "-")
        print("%-6s %-7s %-44s %-13s n=%s" % (ok, row["id"], row["css"][:44], row["fixture"], n))
        for why in row.get("reasons", []):
            print("         - %s" % why)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], os.path.join(HERE, sys.argv[3]) if len(sys.argv) > 3 else HERE)
