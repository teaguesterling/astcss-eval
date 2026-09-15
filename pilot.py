"""Verify a batch of candidate pairs and split it into accepted and rejected.

usage: pilot.py <candidates.jsonl> <batch-id> [root] [--paraphrases=strict|distinct]

--paraphrases=distinct relaxes the content-word overlap rule for training batches
(paraphrases need only differ); the eval keeps the strict default.

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


PARAPHRASE_RULES = ("strict", "distinct")


def static_reasons(p, paraphrase_rule="strict"):
    """paraphrase_rule "strict" (the eval's rule, SPEC.md §5): no two of nl+paraphrases share
    more than half their content words. "distinct" (training batches, Teague 2026-09-15:
    paraphrases may overlap): the texts need only differ after case and whitespace."""
    if paraphrase_rule not in PARAPHRASE_RULES:
        raise ValueError("paraphrase_rule must be one of %s" % (PARAPHRASE_RULES,))
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
            if paraphrase_rule == "distinct":
                if " ".join(texts[i].lower().split()) == " ".join(texts[j].lower().split()):
                    reasons.append("texts %d and %d are the same request" % (i, j))
                continue
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


def request_defects(rows):
    """Training gate (2026-09-15 audit, FINDINGS.md): every request text must determine its selector
    without the fixture. python-b1 verified "functions whose names start with cmd" as
    `.fn[name^="_cmd_"]`, and the trained 0.8B learned to wrap prefixes in underscores.
    audit_pairs.request_reasons lists the rules."""
    import audit_pairs
    bad = {}
    for r in rows:
        hits = []
        for k, t in enumerate([r.get("nl", "")] + (r.get("paraphrases") or [])):
            for why in audit_pairs.request_reasons(r.get("css", ""), t, r.get("fixture")):
                hits.append("text %d %s" % (k, why))
        if hits:
            bad[r["id"]] = "request does not determine the selector: " + "; ".join(hits)
    return bad


def eval_overlap(rows):
    """Training gate: the held-out eval must stay held out.

    A training pair whose request or a paraphrase is an eval request, or (tier 2 and
    above) whose selector is an eval answer, would teach the eval's answers directly,
    whatever the fixture or language: a selector string is language-agnostic. Bare
    tier-1 classes and node types are vocabulary the card already lists, so they are
    allowed. Eval pairs are pairs/{accepted,pending,retired}*.jsonl."""
    norm = lambda s: " ".join(s.lower().split())  # noqa: E731
    ev_nl, ev_css = {}, {}
    # The tier-5 eval (eval_t5/, 2026-09-15) is held out too.
    for path in sorted(glob.glob(os.path.join(HERE, "pairs", "*.jsonl")) + glob.glob(os.path.join(HERE, "eval_t5", "pairs", "*.jsonl"))):
        if os.path.basename(path).startswith("rejected-"):
            continue
        for line in open(path):
            p = json.loads(line)
            for t in [p.get("nl", "")] + (p.get("paraphrases") or []):
                if t:
                    ev_nl[norm(t)] = p["id"]
            if p.get("css"):
                ev_css[p["css"]] = p["id"]
    bad = {}
    for r in rows:
        hits = []
        for t in [r.get("nl", "")] + (r.get("paraphrases") or []):
            if t and norm(t) in ev_nl:
                hits.append('request "%s" is eval pair %s\'s' % (t, ev_nl[norm(t)]))
        if r.get("tier", 0) >= 2 and r.get("css") in ev_css:
            hits.append("selector %s is eval pair %s's answer" % (r["css"], ev_css[r["css"]]))
        if hits:
            bad[r["id"]] = "overlaps the held-out eval: " + "; ".join(hits)
    return bad


def oracle_first_verify(rows):
    """verify.verify's report, with the engine asked only what the oracle can't answer (2026-09-15).

    Every ast_select_from call costs ~6 s of planning (sitting_duck #160), and verify.verify spends
    ~3 of them per pair on relaxations and distractors. Here the engine runs each reference; where
    oracle.py parses the selector and computes the same node set, the relaxations and distractors
    are answered from oracle.Tree. The oracle is trusted only
      - when it reproduces the engine's reference exactly (same digest), and
      - for a relaxation or distractor with no documented-vs-engine difference (oracle.ISSUES features).
    Everything else goes to the engine: whole pairs through verify.verify (unparseable selectors,
    fixtures with no oracle cache, a reference the oracle disagrees with), single relaxations and
    distractors as engine queries. Each entry records how it was decided ("gates": oracle|engine)."""
    import oracle as O
    trees, plan, fallback, queries = {}, {}, [], []
    for r in rows:
        fx, c = r["fixture"], O.parse(r["css"])
        dis = [O.parse(d) for d in r.get("distractors", [])]
        cached = os.path.exists(O.cache(fx, "nodes.csv")) and os.path.exists(O.cache(fx, "atoms.json"))
        if c is None or None in dis or not cached:
            fallback.append(r)
            continue
        plan[r["id"]] = (c, dis)
        queries.append((r["id"] + ":ref", fx, r["css"]))
    got = V.execute(queries) if queries else {}

    report, second, pending = {}, [], {}
    for r in rows:
        if r["id"] not in plan:
            continue
        pid, fx = r["id"], r["fixture"]
        c, dis = plan[pid]
        ref = got[pid + ":ref"]
        if "error" in ref:
            fallback.append(r)       # verify.verify words the error; the query is cached
            continue
        if fx not in trees:
            trees[fx] = O.Tree(fx)
        t = trees[fx]
        oref = t.select(c)
        if t.digest(oref) != V._digest(ref["nodes"]):
            fallback.append(r)
            continue
        checks = [("rel", x) for x in O.relaxed(c)] + [("dis", d) for d in dis]
        answers = []
        for i, (kind, x) in enumerate(checks):
            if O.features(x) & set(O.ISSUES):
                qid = "%s:%s%d" % (pid, kind, i)
                second.append((qid, fx, O.render(x) if kind == "rel" else r["distractors"][i - len(checks) + len(dis)]))
                answers.append((kind, x, qid))
            else:
                answers.append((kind, x, t.select(x) == oref))
        pending[pid] = (r, ref["nodes"], answers)
    got2 = V.execute(second) if second else {}

    for pid, (r, nodes, answers) in pending.items():
        reasons = []
        entry = {"ok": False, "reasons": reasons, "relaxations": [], "distractors": [], "gates": "oracle",
                 "reference": {"count": len(nodes), "sha256": V._digest(nodes), "nodes": nodes}}
        if not V.MIN_NODES <= len(nodes) <= V.MAX_NODES:
            reasons.append("reference returns %d nodes (need %d..%d)" % (len(nodes), V.MIN_NODES, V.MAX_NODES))
        di = 0
        for kind, x, ans in answers:
            by = "oracle"
            if isinstance(ans, str):
                by, e = "engine", got2.get(ans, {"error": "no output for query"})
                ans = e if "error" in e else e["nodes"] == nodes
            if kind == "rel":
                sel, label = O.render(x), "drop to " + O.render(x)
                if isinstance(ans, dict):
                    verdict = "inconclusive: relaxed selector errors"
                    reasons.append("%s -> %s" % (label, verdict))
                elif ans:
                    verdict = "VACUOUS: same %d nodes without it" % len(nodes)
                    reasons.append("%s is not load-bearing" % label)
                else:
                    verdict = "load-bearing"
                entry["relaxations"].append({"label": label, "selector": sel, "verdict": verdict, "by": by})
            else:
                sel = r["distractors"][di]
                di += 1
                if isinstance(ans, dict):
                    verdict = "REJECTED: distractor does not parse/execute"
                    reasons.append("distractor %r errors" % sel)
                elif ans:
                    verdict = "REJECTED: distractor matches the reference"
                    reasons.append("distractor %r matches the reference" % sel)
                else:
                    verdict = "ok"
                entry["distractors"].append({"selector": sel, "verdict": verdict, "by": by})
        entry["ok"] = not reasons
        report[pid] = entry
    if fallback:
        for pid, entry in V.verify(fallback).items():
            report[pid] = dict(entry, gates="engine")
    return report


def main(path, batch, root=HERE, paraphrase_rule="strict", gates="oracle"):
    rows = [json.loads(line) for line in open(path) if line.strip()]
    for r in rows:
        r["selector"] = r["css"]
    # The eval (root == HERE) keeps the engine-only gates it was frozen with.
    report = oracle_first_verify(rows) if gates == "oracle" and os.path.abspath(root) != HERE else V.verify(rows)
    # Training batches only: the eval's pairs were audited by hand (FINDINGS.md).
    has_bad = has_truth_mismatches(rows) if os.path.abspath(root) != HERE else {}
    overlap_bad = eval_overlap(rows) if os.path.abspath(root) != HERE else {}
    request_bad = request_defects(rows) if os.path.abspath(root) != HERE else {}
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
        reasons = static_reasons(r, paraphrase_rule) + list(v["reasons"])
        if r["id"] in has_bad:
            reasons.append(has_bad[r["id"]])
        if r["id"] in overlap_bad:
            reasons.append(overlap_bad[r["id"]])
        if r["id"] in request_bad:
            reasons.append(request_bad[r["id"]])
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
            "paraphrase_rule": paraphrase_rule,
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
    rule = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--paraphrases=")), "strict")
    gates = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--gates=")), "oracle")
    argv = [a for a in sys.argv[1:] if not a.startswith("--")]
    main(argv[0], argv[1], os.path.join(HERE, argv[2]) if len(argv) > 2 else HERE, rule, gates)
