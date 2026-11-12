"""Contrastive pairs for `.def` / `.name` / `.call`, the boundary the vocabulary batch never taught.

WHY THIS BATCH EXISTS. The 491-pair vocabulary batch (train/audit/vocab_pairs.py) taught `.def`
and `.name` from frames with NO contrastive pressure -- every row carried `distractors: []`, and
nothing in the batch ever told the model that "where is X defined" and "every use of X" must get
DIFFERENT answers. Measured consequence, arm D vs the control paired on 298 reworded holdout ids:

    group          n     A orig -> rw           D orig -> rw          D-A
    def-keyword   85   84.7% -> 82.4% (-2.4)  81.2% -> 76.5% (-4.7)   -2.4
    name-keyword  10   30.0% -> 60.0% (+30.0) 40.0% -> 40.0% ( 0.0)  -30.0
    other        203   77.3% -> 78.8% (+1.5)  80.3% -> 72.4% (-7.9)   -9.4

and of D's 27 regressions in `other`, the head class moves `def -> name` 5 times, `call -> fn` 4,
`call -> class` 3. The model answered `.def#X` on the original phrasing (correct) and `.name#X` on
the reworded one. Adding a construct by example teaches its FORM; it does not teach its BOUNDARY.

MINIMAL PAIRS, following train/audit/pseudo_discriminating.py. A declared distractor teaches the
model nothing directly -- it only makes verify.py refuse a pair whose distractor returns the
reference's node set. What teaches a distinction is emitting BOTH selectors as training rows over
the same identifier, each carrying the other as its distractor, with English a careful reader maps
to one and not the other. Where no such English can be written, the pair is dropped.

WHAT IS DELIBERATELY NOT HERE. No `.fn#X` vs `.class#X` contrast. "where is AstVisitor defined"
does not say which kind AstVisitor is, so that family is answerable only by guessing a kind the
request never specifies -- which is the reason `.def` exists. 11 holdout pairs are missed by all
four models tested (including Haiku) for exactly that reason, and the fix there is the suite's,
not the corpus's.

    python3 train/audit/defname_discriminating.py            # candidates -> train/candidates/
"""
import collections, json, os, re

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INV = os.path.join(HERE, "train/audit/inventories/%s.json")
OUT = os.path.join(HERE, "train/candidates/defname-v1.jsonl")

# Held out of training entirely, matching the vocabulary batch's split so the eval stays clean.
HELDOUT_FX = {"py-pluckit", "js-rosetta"}
FX = {"python": ["py-lackpy", "py-blq", "py-pluckit", "py-umwelt"],
      "javascript": ["js-messe", "js-rosetta"], "java": ["java-rosetta"],
      "go": ["go-rosetta"], "c": ["c-duckhts"], "cpp": ["cpp-duckdb-mcp"]}

def names(fx, key):
    raw = json.load(open(INV % fx)).get(key) or ""
    return {m.group(1): int(m.group(2)) for m in re.finditer(r'([\w$]+)\((\d+)\)', raw)}

#: (selector template, [frames]) per role. Each frame names the role EXPLICITLY, because the
#: whole defect is that the roles were taught with interchangeable English.
ROLE = {
 "def": (".def#{n}", [
   "where is {n} defined",
   "the definition of {n}, not the places that use it",
   "take me to {n}'s declaration rather than its call sites",
   "which line declares {n}",
   "{n}'s definition site, not its usages",
   "find where {n} is declared, definition only"]),
 "call": (".call#{n}", [
   "where is {n} called",
   "the call sites of {n}, not its definition",
   "every place {n} is invoked",
   "who calls {n}",
   "find the invocations of {n}, not the declaration",
   "the places that call {n}"]),
 "name": (".name#{n}", [
   "every place the name {n} appears, its definition and its uses alike",
   "all occurrences of the identifier {n}, wherever they are",
   "each mention of the token {n}",
   "anywhere the name {n} is written",
   "every appearance of {n} as a name",
   "the name {n} wherever it occurs"]),
}
PAIRINGS = [("def", "call"), ("def", "name"), ("call", "name")]

def pool_for(fx):
    fns, calls = names(fx, "fn_names"), names(fx, "call_names")
    return [x for x in sorted(set(fns) & set(calls))
            if not x.startswith("__") and fns[x] <= 4 and 2 <= calls[x] <= 25]


def main():
    # Split by NAME, not only by fixture. The rosetta fixtures carry the same function names in
    # several languages ("factorial" is in go-rosetta and js-rosetta alike), so a fixture-only
    # split leaks: the request text AND the selector string are identical across the split, and
    # the model only ever sees NL -> css. pilot.eval_overlap caught 18 such pairs; this is the fix.
    heldout_names = set()
    for fx in HELDOUT_FX:
        if os.path.exists(INV % fx):
            heldout_names |= set(pool_for(fx))
    rows, n = [], 0
    for lang, fixtures in sorted(FX.items()):
        for fx in fixtures:
            if not os.path.exists(INV % fx):
                continue
            fns, calls = names(fx, "fn_names"), names(fx, "call_names")
            # A name needs a definition AND call sites for the three roles to be distinguishable,
            # and every role's node set must plausibly land inside verify's 1..50 bound.
            pool = pool_for(fx)
            if fx not in HELDOUT_FX:
                pool = [x for x in pool if x not in heldout_names]
            pool = pool[:10]
            for name in pool:
                for a, b in PAIRINGS:
                    n += 1
                    for side, (role, other_role) in (("a", (a, b)), ("b", (b, a))):
                        tpl, frames = ROLE[role]
                        css = tpl.replace("{n}", name)
                        other = ROLE[other_role][0].replace("{n}", name)
                        fs = [f.replace("{n}", name) for f in frames]
                        k = (n + len(name)) % len(fs)
                        rows.append({
                            "id": "tr-%s-t5-dn%04d%s" % (lang, n, side), "tier": 5, "fixture": fx,
                            "nl": fs[k], "paraphrases": fs[:k] + fs[k + 1:],
                            "css": css, "distractors": [other], "treeql": None,
                            "construct": role,
                            "tags": ["defname-discriminating", "sitting_duck_supported", "v0"],
                            "contrast": {"kind": "%s_vs_%s" % (a, b), "against": other},
                            "split": "heldout" if fx in HELDOUT_FX else "train"})
    with open(OUT, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    print("wrote %d candidate rows -> %s" % (len(rows), OUT))
    print("by contrast: %s" % dict(collections.Counter(r["contrast"]["kind"] for r in rows)))
    print("by construct: %s" % dict(collections.Counter(r["construct"] for r in rows)))
    print("by split: %s" % dict(collections.Counter(r["split"] for r in rows)))
    print("by language: %s" % dict(collections.Counter(r["id"].split("-")[1] for r in rows)))
    print("distinct (fixture, selector) engine calls: %d"
          % len({(r["fixture"], r["css"]) for r in rows}
                | {(r["fixture"], d) for r in rows for d in r["distractors"]}))
    print("distinct requests: %d" % len({r["nl"] for r in rows}))

if __name__ == "__main__":
    main()
