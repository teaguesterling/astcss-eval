"""Migrate the pairs held pending on #145 from `:scope(X)` to `:in-scope(X)`.

    python3 train/audit/migrate_scope.py                 # dry run
    python3 train/audit/migrate_scope.py --apply         # verify against the new pin and write

182 pairs were written against the documented meaning of `:scope(selector)` -- "inside that scope"
-- because the engine ignored it (#145). sitting_duck 2a1413d gives that meaning its own name,
`:in-scope(X)`, and leaves `:scope` for the boundary test, so the pairs need their selector text
migrated, not their meaning.

Two rewrites, and one shape that cannot migrate:

  :scope(.fn#foo)                -> :in-scope(.fn#foo)                 151 pairs, pure rename
  :scope(function_definition#f)  -> :in-scope(.fn#f)                    31 pairs, argument form too:
      the CSS grammar cannot split `function_definition#f` into type and name, and the engine says
      so loudly ("a #name filter is only supported on the semantic-class form").
  :scope(<full selector>)        -- deferred to #145; none of our pairs use it.

Every rewritten pair is re-verified against the SECOND pin (workspace/engine/sd-20260915-2001,
main d706c89), which is the only build that has :in-scope. sd-20260914-1835 stays authoritative
for scoring, so no measured number moves. A pair whose node set no longer matches what was frozen
is NOT silently re-frozen: it is reported and left out, because a changed node set means the
request may no longer describe the answer.

Run it with the new pin on the environment:

    ENG=workspace/engine/sd-20260915-2001
    SITTING_DUCK=$ENG ASTCSS_MACROS=$ENG/css_selectors.sql python3 train/audit/migrate_scope.py --apply
"""
import collections
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tune"))
import oracle as O  # noqa: E402
import verify as V  # noqa: E402

# Type -> semantic class, for the arguments the grammar cannot express as `type#name`.
TYPE_CLASS = {"function_definition": ".fn", "function_item": ".fn", "method_definition": ".fn",
              "function_declaration": ".fn", "class_definition": ".class", "class_specifier": ".class",
              "struct_specifier": ".class", "class_declaration": ".class", "impl_item": ".class",
              "module": ".mod"}
SOURCES = ("train/pairs/pending-*.jsonl", "workspace/suite1/pairs/pending-*.jsonl")
BATCH = "scope-m1"


def rewrite(css):
    """-> (new css, how) or (None, why not)."""
    if ":scope(" not in css:
        return None, "no :scope( argument"
    m = re.search(r":scope\(([a-z_]+)#(\w+)\)", css)
    if m:
        t, name = m.groups()
        if t not in TYPE_CLASS:
            return None, "no semantic class for %s" % t
        return css.replace(":scope(%s#%s)" % (t, name), ":in-scope(%s#%s)" % (TYPE_CLASS[t], name)), \
            "argument rewritten to the semantic-class form"
    return css.replace(":scope(", ":in-scope("), "renamed"


def load():
    rows = []
    for pat in SOURCES:
        for path in sorted(glob.glob(os.path.join(HERE, pat))):
            for line in open(path):
                p = json.loads(line)
                if any("scope-selector" in t for t in p.get("tags", [])):
                    rows.append((p, os.path.relpath(path, HERE)))
    return rows


def taken_node_sets(skip_ids):
    """(fixture, sha) -> id for every pair already frozen, EXCLUDING the ones being migrated --
    otherwise each migrated pair collides with its own pending original."""
    taken = {}
    for pat in ("train/pairs/accepted-*.jsonl", "workspace/suite1/pairs/kept-*.jsonl"):
        for path in glob.glob(os.path.join(HERE, pat)):
            for line in open(path):
                p = json.loads(line)
                if p["id"] in skip_ids or not p.get("reference"):
                    continue
                taken[(p["fixture"], p["reference"]["sha256"])] = p["id"]
    return taken


def main(argv):
    apply = "--apply" in argv
    pairs = load()
    print("pending on #145: %d pairs" % len(pairs))
    rows, skipped, how = [], [], collections.Counter()
    for p, src in pairs:
        css, why = rewrite(p["css"])
        if css is None:
            skipped.append((p["id"], p["css"], why))
            continue
        c = O.parse(css)
        dis = [O.parse(rewrite(d)[0] or d) for d in (p.get("distractors") or [])]
        if c is None or any(d is None for d in dis):
            skipped.append((p["id"], css, "oracle cannot parse the rewritten selector"))
            continue
        how[why] += 1
        rows.append({"id": p["id"], "fixture": p["fixture"], "nl": p["nl"], "paraphrases": p["paraphrases"],
                     "struct": c, "distractor_structs": dis, "was": p["css"],
                     "frozen": p["reference"]["sha256"], "src": src})
    print("rewritten: %s" % dict(how))
    for s in skipped[:6]:
        print("  skipped %-24s %-44s %s" % s)
    if len(skipped) > 6:
        print("  ... and %d more skipped" % (len(skipped) - 6))
    if not apply:
        print("\ndry run: nothing written (--apply to verify against the new pin and write)")
        return 0

    print("\nengine: %s" % json.dumps(V.engine_identity())[:150])
    out, meta = O.verify_batch([{k: r[k] for k in ("id", "fixture", "nl", "paraphrases", "struct",
                                                   "distractor_structs")} for r in rows],
                               BATCH, os.path.join(HERE, "workspace", BATCH), "distinct",
                               check_eval_overlap=True,
                               taken=taken_node_sets({r["id"] for r in rows}))
    frozen = {r["id"]: r["frozen"] for r in rows}
    moved = [r for r in out["accepted"] if r["reference"]["sha256"] != frozen[r["id"]]]
    print(json.dumps({k: meta[k] for k in ("candidates", "accepted", "pending", "rejected")}))
    print("accepted whose node set CHANGED (left for review, not re-frozen silently): %d" % len(moved))
    for r in moved[:8]:
        print("   %-24s %-46s %d nodes now" % (r["id"], r["css"][:46], r["reference"]["count"]))
    for r in out["rejected"][:6]:
        print("   rejected %-22s %s" % (r["id"], "; ".join(r["reasons"])[:90]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
