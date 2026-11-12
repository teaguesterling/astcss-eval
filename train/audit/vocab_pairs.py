"""Training pairs for the 35 constructs the card never documented.

WHY. The card teaches ~40 constructs and the engine supports ~75. The corpus inherited exactly
the documented half: 0 of 8,326 pairs use `.def`, `.name`, `.block`, `[peek*=]`, `[qualified*=]`,
`::parent`, `:first-child` or any of the rest. Both evals were written from the corpus, so
nothing measured this session could see the other half existed. 95% of the 9B's named-lookup
failures on the holdout are right-name-wrong-class -- it is guessing a KIND the English never
specified, which `.def#X` makes unnecessary.

VARIETY, because the register lesson cost 12 points once already: each construct carries many
hand-written frames across registers -- terse, imperative, interrogative, conversational -- and
is instantiated over real identifiers from the fixture inventories.

NARROW BY CONSTRUCTION. `.name` is 9,964 nodes on py-lackpy and verify needs 1..50, so every
frame below is either name-qualified (`.def#X`) or scoped (`.fn#X .block`). A bare `.name` is
not an answerable request anyway.
"""
import json, os, random, re, sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
INV = os.path.join(HERE, "train/audit/inventories/%s.json")
FX = {"python": ["py-lackpy", "py-blq", "py-pluckit"], "javascript": ["js-messe", "js-rosetta"],
      "java": ["java-rosetta"], "rust": ["rs-magic", "rs-cosmic-goo"], "go": ["go-rosetta"],
      "c": ["c-duckhts"], "bash": ["sh-homelab"]}

def names(fx, key):
    raw = json.load(open(INV % fx))[key]
    return {m.group(1): int(m.group(2)) for m in re.finditer(r'([\w$]+)\((\d+)\)', raw)}

#: construct -> (selector template, [request frames]).  {n}=identifier {c}=class {l}=language
SPEC = {
 "def": (".def#{n}", [
   "where is {n} defined", "find the definition of {n}", "take me to {n}'s definition",
   "which file declares {n}", "show me where {n} is declared", "the declaration of {n}",
   "I need {n}'s definition, whatever kind of thing it is",
   "where does {n} get defined?", "point me at the definition of {n}",
   "jump to whatever defines {n}", "{n} -- where is it declared",
   "locate the {n} declaration"]),
 "name": (".name#{n}", [
   "what references {n}", "every use of {n}", "where is {n} referred to",
   "find the places {n} is mentioned", "all occurrences of the name {n}",
   "who uses {n}?", "show the references to {n}", "every mention of {n}",
   "where does the name {n} appear", "usages of {n}", "{n} references",
   "which places name {n}"]),
 "parent": (".call#{n}::parent", [
   "what encloses the calls to {n}", "the parent node of each {n} call",
   "whatever directly contains a call to {n}", "step up one level from every {n} call",
   "the syntactic parent of the {n} calls", "what holds each call to {n}"]),
 "scope": (".call#{n}::scope", [
   "which scope contains each call to {n}", "the enclosing scope of every {n} call",
   "what scope does each {n} call sit in", "the scopes around calls to {n}",
   "for each {n} call, the scope it lives in"]),
 "peek": ('.fn[peek*="{t}"]', [
   "functions whose source mentions {t}", "functions containing the text {t}",
   "search the function bodies for {t}", "which functions have {t} written in them",
   "functions with {t} somewhere in the source", "grep the functions for {t}",
   "any function whose text includes {t}"]),
 "qualified": ('.fn[qualified*="{c}"]', [
   "the methods of {c}", "functions whose qualified name mentions {c}",
   "everything under {c} by name", "{c}'s own functions, by qualified name",
   "functions belonging to {c}", "which functions are qualified by {c}"]),
 "firstchild": (".class#{c} .fn:first-child", [
   "the first method declared in {c}", "{c}'s first function",
   "whichever method comes first in {c}", "the opening method of {c}",
   "first thing {c} defines"]),
 "block": (".fn#{n} .block", [
   "the blocks inside {n}", "{n}'s nested bodies", "what blocks does {n} contain",
   "the bodies within {n}", "block structures inside {n}"]),
 "access": (".fn#{n} .access", [
   "attribute accesses inside {n}", "what does {n} reach into",
   "the dotted lookups in {n}", "subscripts and attributes within {n}",
   "accesses performed by {n}"]),
 "literal": (".fn#{n} .literal", [
   "literals inside {n}", "the constants {n} uses", "hard-coded values in {n}",
   "what literals appear in {n}", "{n}'s inline values"]),
}
TEXTS = ["TODO", "raise", "return", "self", "import", "assert", "None", "error", "with"]

def main():
    rnd = random.Random("vocab-v1")
    rows, seen, i = [], set(), 0
    for lang, fixtures in sorted(FX.items()):
        for fx in fixtures:
            fns = names(fx, "fn_names"); cls = names(fx, "class_names"); calls = names(fx, "call_names")
            uniq_fn = [n for n, c in fns.items() if c == 1 and not n.startswith("__")][:18]
            uniq_cl = [n for n, c in cls.items() if c == 1][:10]
            uniq_ca = [n for n, c in calls.items() if 2 <= c <= 25][:14]
            for key, (tpl, frames) in sorted(SPEC.items()):
                pool = (uniq_cl if "{c}" in tpl else
                        uniq_ca if key in ("parent", "scope") else
                        TEXTS if "{t}" in tpl else uniq_fn)
                for j, val in enumerate(pool[:8]):
                    css = tpl.replace("{n}", str(val)).replace("{c}", str(val)).replace("{t}", str(val))
                    nl = frames[(i + j) % len(frames)].replace("{n}", str(val)) \
                           .replace("{c}", str(val)).replace("{t}", str(val)).replace("{l}", lang)
                    k = (fx, css)
                    if k in seen: continue
                    seen.add(k); i += 1
                    rows.append({"id": "tr-%s-t5-vb%04d" % (lang, i), "tier": 5, "fixture": fx,
                                 "nl": nl, "paraphrases": [], "css": css, "distractors": [],
                                 "treeql": None, "construct": key,
                                 "tags": ["vocab-v2", "undocumented-construct", "v0"]})
    p = os.path.join(HERE, "train/candidates/vocab-v2.jsonl")
    with open(p, "w") as fh:
        for r in rows: fh.write(json.dumps(r) + "\n")
    import collections
    print("%d candidates -> %s" % (len(rows), p))
    print("by construct: %s" % dict(collections.Counter(r["construct"] for r in rows)))
    print("by language:  %s" % dict(collections.Counter(r["id"].split("-")[1] for r in rows)))
    print("distinct requests: %d" % len({r["nl"] for r in rows}))

if __name__ == "__main__":
    main()
