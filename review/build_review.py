"""Build the pair review page: every training, validation and eval pair with its audit flags.

    python3 review/build_review.py                      # train, val, eval, eval_t5, retired
    python3 review/build_review.py --include suite1     # + workspace/suite1/pairs/kept-suite1.jsonl

Writes review/pairs-review.html (a standalone page: open it in a browser, annotations stay in
that browser's storage and export as JSON) and workspace/review/artifact.html (the same page
without the document shell, for publishing as an Artifact, where annotations sync to the
page's store so Claude can read them back).

Each text carries the audit's flags: "gate" is audit_pairs.request_reasons (the rule pilot.py
now enforces on training batches), "hint" is the heuristic structure check and any name
literal the text never mentions. The validation split is recomputed exactly as
tune/build_dataset.py does it (seeded hash of the pair id, default seed and fraction).
"""
import argparse
import datetime
import glob
import hashlib
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import audit_pairs as A  # noqa: E402

# tune/build_dataset.py: --seed astcss-train-v1, --val-frac 0.1, split = hash(seed + ":split", id)
SPLIT_SEED, VAL_FRAC = "astcss-train-v1", 0.1
FIXTURE_LANG = {"py": "python", "js": "javascript", "rs": "rust", "go": "go", "java": "java", "c": "c",
                "cpp": "cpp", "sql": "sql", "sh": "bash", "repo": "python", "oracle": "python"}
SETS = [
    ("train", "Training", "train/pairs/accepted-*.jsonl, training split"),
    ("val", "Validation", "train/pairs/accepted-*.jsonl, held-out validation split (10% by id hash)"),
    ("eval", "Eval (T1-T4)", "pairs/accepted-* and pending-*: the 108-pair test set; the model is asked text 0"),
    ("eval_t5", "Eval (T5)", "eval_t5/pairs: the tier-5 test set; the model is asked text 0"),
    ("retired", "Retired", "originals replaced or withdrawn (train/pairs/retired.jsonl, pairs/retired.jsonl)"),
    ("suite1", "Suite 1", "generated selector-first pairs that passed the filter stage (not yet trained on)"),
]


def val_split(pair_id):
    h = hashlib.sha256(("%s:%s" % (SPLIT_SEED + ":split", pair_id)).encode()).hexdigest()
    return "val" if int(h[:8], 16) / 0x100000000 < VAL_FRAC else "train"


def lang_of(p):
    if p["id"].startswith("tr-"):
        return p["id"].split("-")[1]
    fx = p.get("fixture") or ""
    return FIXTURE_LANG.get(fx.split("-")[0], fx.split("-")[-1])


def load(pattern):
    rows = []
    for path in sorted(glob.glob(os.path.join(HERE, pattern))):
        for line in open(path):
            if line.strip():
                rows.append((json.loads(line), os.path.relpath(path, HERE)))
    return rows


def flags_for(p):
    out = []
    texts = [p["nl"]] + list(p.get("paraphrases") or [])
    lits = A.literals(p["css"])
    for k, t in enumerate(texts):
        gate = A.request_reasons(p["css"], t, p.get("fixture"))
        for why in gate:
            out.append([k, "gate", why])
        for rule, why in A.structure_findings(p["css"], t):
            if rule == "referential" and any("points outside" in g for g in gate):
                continue
            out.append([k, "hint", why])
        if not gate:
            for kind, attr, op, v in lits:
                if kind != "attr" and A.presence(t, v) == "absent":
                    out.append([k, "hint", "never names %s (fine for a well-known API, not for a project name)" % v])
    return out


def record(p, set_key, path):
    ref = p.get("reference") or {}
    rec = {
        "id": p["id"], "set": set_key, "lang": lang_of(p), "tier": p.get("tier"), "fixture": p.get("fixture"),
        "css": p["css"], "texts": [p["nl"]] + list(p.get("paraphrases") or []),
        "lits": sorted({v for _, _, _, v in A.literals(p["css"]) if v.strip("_")}),
        "flags": flags_for(p), "count": ref.get("count"), "nodes": (ref.get("nodes") or [])[:8],
        "batch": (p.get("verification") or {}).get("batch"), "tags": p.get("tags") or [], "file": path,
        "distractors": p.get("distractors") or [],
    }
    for k in ("replaced_by", "reason", "retired"):
        if p.get(k):
            rec[k] = p[k]
    return rec


def git_ident():
    try:
        sha = subprocess.check_output(["git", "-C", HERE, "rev-parse", "--short", "HEAD"], text=True).strip()
        dirty = subprocess.call(["git", "-C", HERE, "diff", "--quiet"]) != 0
        return sha + ("+dirty" if dirty else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--include", default="", help="comma-separated extra sets: suite1")
    ap.add_argument("--out", default="review/pairs-review.html")
    ap.add_argument("--artifact-out", default="workspace/review/artifact.html")
    args = ap.parse_args(argv)
    extra = set(filter(None, args.include.split(",")))

    pairs = []
    for p, path in load("train/pairs/accepted-*.jsonl"):
        pairs.append(record(p, val_split(p["id"]), path))
    for p, path in load("pairs/accepted-*.jsonl") + load("pairs/pending-*.jsonl"):
        pairs.append(record(p, "eval", path))
    for p, path in load("eval_t5/pairs/accepted-*.jsonl") + load("eval_t5/pairs/pending-*.jsonl"):
        pairs.append(record(p, "eval_t5", path))
    for p, path in load("train/pairs/retired.jsonl") + load("pairs/retired.jsonl"):
        if "css" in p and "nl" in p:
            p.setdefault("paraphrases", [])
            pairs.append(record(p, "retired", path))
    if "suite1" in extra:
        for p, path in load("workspace/suite1/pairs/kept-suite1.jsonl"):
            pairs.append(record(p, "suite1", path))

    # Claude's own review (review/claude-review-*.json, later files win per pair): shown read-only
    # beside the viewer's annotations. Pairs a file lists as reviewed but doesn't annotate are "ok".
    for path in sorted(glob.glob(os.path.join(HERE, "review", "claude-review-*.json"))):
        rv = json.load(open(path))
        notes = rv.get("pairs", {})
        reviewed = set(rv.get("reviewed", [])) | set(notes)
        for r in pairs:
            if r["set"] == "retired" or r["id"] not in reviewed:
                continue
            r["claude"] = dict(notes.get(r["id"]) or {"verdict": "ok"}, source=os.path.basename(path))

    present = {r["set"] for r in pairs}
    payload = {
        "schema": "astcss-review-data/1",
        "built": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "git": git_ident(),
        "sets": [{"key": k, "label": l, "desc": d} for k, l, d in SETS if k in present],
        "pairs": pairs,
    }
    payload["version"] = hashlib.sha256(json.dumps(pairs, sort_keys=True).encode()).hexdigest()[:12]
    blob = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    template = open(os.path.join(HERE, "review", "review_template.html")).read()
    content = template.replace("__REVIEW_DATA__", blob)

    standalone = ('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
                  '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
                  '</head>\n<body>\n' + content + '\n</body>\n</html>\n')
    for dest, text in ((args.out, standalone), (args.artifact_out, content)):
        dest = os.path.join(HERE, dest)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "w") as fh:
            fh.write(text)
    counts = {}
    for r in pairs:
        counts[r["set"]] = counts.get(r["set"], 0) + 1
    gated = sum(1 for r in pairs if any(f[1] == "gate" for f in r["flags"]) and r["set"] in ("train", "val"))
    print("wrote %s and %s: %s; %d training/validation pairs still gate-flagged; data %s, %d KB"
          % (args.out, args.artifact_out, counts, gated, payload["version"], len(blob) // 1024))


if __name__ == "__main__":
    main(sys.argv[1:])
