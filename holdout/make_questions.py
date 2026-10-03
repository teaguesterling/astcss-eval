"""Write the holdout suite's questions.

DIFFERENT QUESTIONS, deliberately. Every phrasing here is written for this suite and appears
in no training pair and no other eval: pseudo-d3's lesson was that 152 pairs drawn from six
templates teach the templates, so a validation suite built from training's phrasings would
measure the wrong thing. The wording is also varied in REGISTER, not just vocabulary -- some
requests read like a code-review question, some like a grep, some like a half-remembered
name -- because that is the spread real use has.

Each question is instantiated against a selector whose node count the engine has already
reported in 1..50 (verify's reference bound), so the suite is answerable by construction.

COVERAGE is by selector FAMILY, one family per question shape, so a per-family score is
readable later:
    bare class      .fn .class .call .loop .if .try .var .import .member .jump
    named           .fn#name  .call#name  .class#Name
    has/not         .fn:has(X)  .fn:not(:has(X))
    descendant      .class#N .fn   .fn .call
    child           .class#N > .fn
    attribute       .call[receiver="x"]  .fn[name^="x"]
"""
import json, os, re, sys, collections

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import verify as V

FXLANG = {k: v["language"] for k, v in
          json.load(open(os.path.join(HERE, "holdout/fixtures/MANIFEST.json")))["fixtures"].items()}

#: (selector template, [question phrasings]) -- %(l)s is the language word, %(n)s a real name
BARE = [
    (".fn",      ["where are the {l} functions defined", "list every function definition",
                  "I need all the function bodies in this {l} code",
                  "show me the routines declared here"]),
    (".class",   ["which classes does this {l} code define", "every class declaration, please",
                  "find the type definitions", "what classes live in here"]),
    (".call",    ["every place this code invokes something", "all the call sites",
                  "where does it call out to anything", "show the invocations"]),
    (".loop",    ["any loop in this {l} source", "where does it iterate",
                  "find the loops", "show me the iteration constructs"]),
    (".if",      ["the conditional branches", "where does this code branch",
                  "every if construct", "find the branching logic"]),
    (".try",     ["anywhere it guards against failure", "the error-handling blocks",
                  "where is exception handling set up", "find the try blocks"]),
    (".import",  ["what does this {l} file pull in", "the import statements",
                  "where are dependencies brought in", "show the includes"]),
    (".member",  ["attribute and field accesses", "where does it reach into an object",
                  "the member lookups", "every dotted access"]),
    (".jump",    ["the early exits", "where does control leave a block",
                  "return and break statements", "find the jumps out"]),
    (".var",     ["the variables this code declares", "every binding introduced here",
                  "where are locals defined", "show the declarations"]),
]
NAMED_FN = ["where is {n} defined", "find the definition of {n}", "take me to {n}",
            "I am looking for the {n} function", "show me {n}'s body"]
NAMED_CALL = ["every call to {n}", "where does anything invoke {n}",
              "find the {n} call sites", "who calls {n}"]
NAMED_CLASS = ["the {n} class", "where is {n} declared", "find class {n}",
               "show me the {n} type"]
HAS = ["functions that contain {d}", "any function with {d} inside it",
       "which functions have {d} in the body", "routines wrapping {d}"]
HASNOT = ["functions with no {d} at all", "functions that never use {d}",
          "routines free of {d}", "which functions avoid {d}"]
DESC = ["{nd} inside the {n} class", "the {nd} declared within {n}",
        "what {nd} does {n} contain", "{n}'s own {nd}"]

DESC_WORD = {".fn": "methods", ".call": "calls", ".var": "variables", ".if": "conditionals"}
INNER_WORD = {".call": "a call", ".loop": "a loop", ".if": "a branch", ".try": "error handling",
              ".member": "an attribute access", ".jump": "an early return"}


def names(fx, cls, cap=40):
    """Real identifiers in this fixture, read off the engine rather than guessed."""
    got = V.execute([("n", fx, cls)])["n"]
    if "error" in got:
        return []
    # node ids look like "path:line"; names need a second query per candidate, so instead
    # ask the engine for named variants of a shortlist discovered from the source text
    return []


def main():
    counts = json.load(open(os.path.join(HERE, "workspace/holdout_counts.json")))
    rows, i = [], 0
    for fx, lang in sorted(FXLANG.items()):
        for sel, phr in BARE:
            n = counts.get("%s|%s" % (fx, sel), -1)
            if not (1 <= n <= 50):
                continue
            i += 1
            q = phr[i % len(phr)].format(l=lang)
            rows.append({"id": "ho-%04d" % i, "tier": 5, "fixture": fx, "lang": lang,
                         "nl": q, "paraphrases": [], "css": sel, "distractors": [],
                         "treeql": None, "family": "bare",
                         "tags": ["holdout", "never-train", "v0"]})
    with open(os.path.join(HERE, "holdout/pairs/draft-bare.jsonl"), "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    print("bare-class questions in bounds: %d" % len(rows))
    print("by fixture: %s" % dict(collections.Counter(r["fixture"] for r in rows)))
    print("by selector: %s" % dict(collections.Counter(r["css"] for r in rows)))


if __name__ == "__main__":
    main()
