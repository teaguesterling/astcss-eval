"""Prefix and suffix pairs whose requests state the filter value literally, mostly without underscores.

The 2026-09-15 audit (FINDINGS.md) found training requests like "functions whose names start with
cmd" verified as `.fn[name^="_cmd_"]`, and the trained 0.8B learned to wrap prefixes in
underscores ("starts with add" -> `^="_add_"`). These candidates teach the literal mapping on
real fixture names, and contrast values on one stem ("get" / "get_" / "_get_") where the fixture
makes them select different nodes, so the underscore is only ever there when the request says so.

Names come from the oracle's node cache (workspace/oracle/<fixture>/nodes.csv); counts here are
approximate, pilot.py decides what is kept (bounds, load-bearing, distractors, duplicates, eval
overlap, and the request gate).

    python3 train/audit/prefix_contrast.py > train/candidates/prefix-c1.jsonl
    python3 pilot.py train/candidates/prefix-c1.jsonl prefix-c1 train --paraphrases=distinct
"""
import collections
import csv
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, HERE)
import audit_pairs  # noqa: E402

LANGS = {"py": "python", "js": "javascript", "rs": "rust", "go": "go", "java": "java", "c": "c", "cpp": "cpp",
         "sql": "sql"}
# kind -> (selector, node test on a nodes.csv row, plural noun, other kind's selector for a distractor)
KINDS = {
    "fn": (".fn", lambda r: r["sem"] == "DEFINITION_FUNCTION", "functions", "definitions"),
    "call": (".call", lambda r: r["sem"] == "COMPUTATION_CALL", "calls", "call sites"),
}
SQL_KINDS = {
    "call": ("invocation", lambda r: r["type"] == "invocation", "calls", "invocations"),
}
TEMPLATES = {
    "^=": ["{noun} whose names start with {v}", "which {noun} begin with {v}?", "find {alt} prefixed {v}"],
    "$=": ["{noun} whose names end with {v}", "which {noun} end in {v}?", "find {alt} with the {v} suffix"],
}
PER_GROUP = 3        # values per (fixture, kind, op)
MAX_COUNT = 30


def fixture_lang(fx):
    return LANGS.get(fx.split("-", 1)[0])


def names_by_kind(fx):
    path = os.path.join(HERE, "workspace", "oracle", fx, "nodes.csv")
    if not os.path.exists(path):
        return {}
    csv.field_size_limit(10 ** 9)
    kinds = SQL_KINDS if fixture_lang(fx) == "sql" else KINDS
    out = {k: [] for k in kinds}
    for r in csv.DictReader(open(path)):
        if not r["name"]:
            continue
        for k, (_, test, _, _) in kinds.items():
            if test(r):
                out[k].append(r["name"])
    return out


def prefix_values(name):
    """Candidate ^= values a person would name: the first word, with and without its separator."""
    vals = set()
    m = re.match(r"^(_*)([A-Za-z][a-z0-9]*|[A-Z]+(?=[A-Z][a-z]))(_?)", name)
    if not m:
        return vals
    lead, word, sep = m.groups()
    if len(word) < 3:
        return vals
    vals.add(lead + word)
    if sep:
        vals.add(lead + word + sep)
    return vals


def suffix_values(name):
    vals = set()
    m = re.search(r"(_?)([A-Z][a-z0-9]+|[a-z0-9]{2,})(_*)$", name)
    if not m:
        return vals
    sep, word, trail = m.groups()
    if len(word) < 2 or word == name:
        return vals
    vals.add(word + trail)
    if sep:
        vals.add(sep + word + trail)
    return vals


def eval_selectors():
    css = set()
    for path in glob.glob(os.path.join(HERE, "pairs", "*.jsonl")) + glob.glob(os.path.join(HERE, "eval_t5", "pairs", "*.jsonl")):
        for line in open(path):
            css.add(json.loads(line).get("css"))
    return css


def main():
    taken = eval_selectors()
    for path in glob.glob(os.path.join(HERE, "train", "pairs", "accepted-*.jsonl")):
        for line in open(path):
            p = json.loads(line)
            taken.add((p["fixture"], p["css"]))
    fixtures = sorted(os.path.basename(d) for d in glob.glob(os.path.join(HERE, "workspace", "oracle", "*"))
                      if fixture_lang(os.path.basename(d)) and os.path.isdir(os.path.join(HERE, "train", "fixtures", os.path.basename(d))))
    rows, serial, shape = [], collections.Counter(), collections.Counter()
    for fx in fixtures:
        lang = fixture_lang(fx)
        kinds = SQL_KINDS if lang == "sql" else KINDS
        by_kind = names_by_kind(fx)
        for kind, names in by_kind.items():
            sel, _, noun, alt = kinds[kind]
            other = next((kinds[k][0] for k in kinds if k != kind), None)
            for op, values_of, test in (("^=", prefix_values, str.startswith), ("$=", suffix_values, str.endswith)):
                counts = collections.Counter()
                for n in set(names):
                    for v in values_of(n):
                        counts[v] = 0
                for v in counts:
                    counts[v] = sum(1 for n in names if test(n, v))
                ok = {v: c for v, c in counts.items() if 2 <= c <= MAX_COUNT and c < len(names)}
                stems = collections.defaultdict(list)
                for v in ok:
                    stems[v.strip("_").lower()].append(v)
                # contrast stems first (two spellings selecting different counts), then plain values
                contrast = [sorted(vs, key=len) for s, vs in stems.items()
                            if len(vs) > 1 and len({ok[v] for v in vs}) > 1]
                plain = [v for v in sorted(ok, key=lambda v: -ok[v]) if "_" not in v]
                chosen = []
                for vs in sorted(contrast, key=lambda vs: -sum(ok[v] for v in vs))[:1]:
                    chosen += vs[:2]
                for v in plain:
                    if len(chosen) >= PER_GROUP:
                        break
                    if v not in chosen:
                        chosen.append(v)
                for v in chosen:
                    css = '%s[name%s"%s"]' % (sel, op, v)
                    if css in taken or (fx, css) in taken:
                        continue
                    sib = [w for w in stems[v.strip("_").lower()] if w != v]
                    distractors = [sel]
                    distractors += ['%s[name%s"%s"]' % (sel, op, w) for w in sib[:1]]
                    if other:
                        distractors.append('%s[name%s"%s"]' % (other, op, v))
                    serial[lang] += 1
                    texts = [t.format(noun=noun, alt=alt, v=v) for t in TEMPLATES[op]]
                    row = {"id": "tr-%s-t2-x%04d" % (lang, serial[lang]), "tier": 2, "fixture": fx,
                           "nl": texts[0], "paraphrases": texts[1:], "css": css, "distractors": distractors,
                           "treeql": None}
                    bad = [r for t in texts for r in audit_pairs.request_reasons(css, t, fx)]
                    if bad:
                        print("skip %s %s: %s" % (fx, css, bad[0]), file=sys.stderr)
                        continue
                    shape["underscore" if "_" in v else "plain"] += 1
                    rows.append(row)
    for r in rows:
        print(json.dumps(r, ensure_ascii=False))
    print("%d candidates; by language %s; values %s" % (len(rows), dict(serial), dict(shape)), file=sys.stderr)


if __name__ == "__main__":
    main()
