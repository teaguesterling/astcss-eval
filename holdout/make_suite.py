"""Build the holdout validation suite: questions written for this suite and nowhere else.

WHY THE WORDING MATTERS. pseudo-d3 showed that 152 pairs drawn from six templates teach the
templates, and an eval built from training's phrasings cannot tell learning from recall. So
every phrasing below is written here, varied in REGISTER as well as vocabulary -- some read
like a code-review question, some like a grep, some like a half-remembered name -- and none
is reused from train/ or eval_t5. pilot.eval_overlap enforces the converse direction (no
training pair may match this suite), which is what makes it a holdout rather than a promise.

WHY MOSTLY SPECIFIC QUESTIONS. verify.py needs a reference in 1..50 nodes, and these are real
repos: ho-ts-cockpit has 1,270 `.fn`, so "every function" is unanswerable as a reference on
most fixtures. Only 26 bare-class questions fit. Named selectors, :has/:not and descendants
land in range naturally -- and are closer to what anyone actually asks.

Candidates are generated generously; the engine gate decides. Out-of-bounds and vacuous ones
are SUPPOSED to be rejected.
"""
import json, os, re, sys, collections

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAN = json.load(open(os.path.join(HERE, "holdout/fixtures/MANIFEST.json")))["fixtures"]
LANG = {k: v["language"] for k, v in MAN.items()}
NAMES = json.load(open(os.path.join(HERE, "workspace/holdout_names.json")))
COUNTS = json.load(open(os.path.join(HERE, "workspace/holdout_counts.json")))

def parse(fx, kind, lo=1, hi=40):
    s = NAMES.get("%s|%s" % (fx, kind), "") or ""
    out = [(m.group(1), int(m.group(2))) for m in re.finditer(r'([A-Za-z_][\w$?!]*)\((\d+)\)', s)]
    return [(n, c) for n, c in out if lo <= c <= hi]

# ---- phrasings, one bank per family, all written for this suite ---------------------
FN_NAMED = ["where is {n} defined", "take me to {n}", "I need the body of {n}",
            "find where {n} is declared", "jump to the {n} definition",
            "which file holds {n}", "show me {n}"]
CLASS_NAMED = ["the {n} class", "where is {n} declared", "find the {n} type",
               "show me class {n}", "point me at {n}'s declaration"]
CALL_NAMED = ["every call to {n}", "who invokes {n}", "find the {n} call sites",
              "where is {n} actually used", "all the places {n} gets called"]
HAS = ["{w} that contain {d}", "any {w} with {d} inside", "which {w} have {d} in them",
       "{w} wrapping {d}", "{w} where {d} appears"]
NOT = ["{w} with no {d} anywhere", "{w} that never touch {d}", "{w} free of {d}",
       "which {w} avoid {d} entirely", "{w} without {d}"]
DESC = ["the methods inside {n}", "what does {n} define", "{n}'s own methods",
        "functions declared within {n}", "members {n} declares"]
CHILD = ["methods directly on {n}, not nested deeper", "{n}'s immediate methods only",
         "methods one level inside {n}", "direct children of {n} that are functions"]
BARE = {".fn": ["where are the {l} functions", "every function definition in this {l} code",
                "list the routines", "show all function bodies"],
        ".class": ["which classes does this {l} code define", "every class declaration",
                   "find the type definitions", "what classes are here"],
        ".call": ["every invocation", "all the call sites", "where does it call out",
                  "show the calls"],
        ".loop": ["any loop here", "where does it iterate", "find the loops",
                  "the iteration constructs"],
        ".if": ["the conditional branches", "where does this branch", "every if construct",
                "find the branching"],
        ".try": ["the error-handling blocks", "where failure is guarded",
                 "exception handling sites", "find the try blocks"],
        ".import": ["what this {l} file pulls in", "the imports", "where dependencies come in",
                    "show the includes"],
        ".member": ["attribute accesses", "where it reaches into an object", "member lookups",
                    "every dotted access"],
        ".jump": ["the early exits", "return and break statements", "where control leaves",
                  "find the jumps out"],
        ".var": ["the variables declared", "every binding here", "where locals are defined",
                 "show the declarations"]}
INNER = [(".call", "a call"), (".loop", "a loop"), (".if", "a branch"),
         (".try", "error handling"), (".member", "an attribute access"), (".jump", "an early return")]
WORD = {"python": "functions", "ruby": "methods", "javascript": "functions", "typescript": "functions",
        "java": "methods", "c": "functions", "cpp": "functions", "go": "functions",
        "rust": "functions", "bash": "functions", "sql": "macros"}

def main():
    rows, i = [], 0
    def add(fx, css, nl, fam):
        nonlocal i
        i += 1
        rows.append({"id": "ho-%04d" % i, "tier": 5, "fixture": fx, "lang": LANG[fx],
                     "nl": nl, "paraphrases": [], "css": css, "distractors": [],
                     "treeql": None, "family": fam, "tags": ["holdout", "never-train", "v0"]})
    for fx in sorted(MAN):
        lang = LANG[fx]; w = WORD.get(lang, "functions")
        for j, (n, c) in enumerate(parse(fx, "fn")[:14]):
            add(fx, ".fn#%s" % n, FN_NAMED[j % len(FN_NAMED)].format(n=n), "named-fn")
        for j, (n, c) in enumerate(parse(fx, "class")[:8]):
            add(fx, ".class#%s" % n, CLASS_NAMED[j % len(CLASS_NAMED)].format(n=n), "named-class")
        for j, (n, c) in enumerate(parse(fx, "call", 2, 30)[:10]):
            add(fx, ".call#%s" % n, CALL_NAMED[j % len(CALL_NAMED)].format(n=n), "named-call")
        for j, (inner, dword) in enumerate(INNER):
            if COUNTS.get("%s|%s" % (fx, inner), 0) > 0:
                add(fx, ".fn:has(%s)" % inner, HAS[j % len(HAS)].format(w=w, d=dword), "has")
                add(fx, ".fn:not(:has(%s))" % inner, NOT[j % len(NOT)].format(w=w, d=dword), "not")
        for j, (n, c) in enumerate(parse(fx, "class")[:6]):
            add(fx, ".class#%s .fn" % n, DESC[j % len(DESC)].format(n=n), "descendant")
            add(fx, ".class#%s > .fn" % n, CHILD[j % len(CHILD)].format(n=n), "child")
        for css, phr in BARE.items():
            cnt = COUNTS.get("%s|%s" % (fx, css), -1)
            if 1 <= cnt <= 50:
                add(fx, css, phr[i % len(phr)].format(l=lang), "bare")
    p = os.path.join(HERE, "holdout/pairs/candidates.jsonl")
    with open(p, "w") as fh:
        for r in rows: fh.write(json.dumps(r) + "\n")
    print("%d candidates -> %s" % (len(rows), p))
    print("by family:  %s" % dict(collections.Counter(r["family"] for r in rows)))
    print("by language: %s" % dict(collections.Counter(r["lang"] for r in rows)))
    print("distinct phrasings: %d" % len({r["nl"] for r in rows}))

if __name__ == "__main__":
    main()
