"""The abstention suite: requests astcss CANNOT express, plus answerable controls.

WHY THIS DID NOT EXIST. Across all 536 eval pairs in this project, zero are unanswerable, and
every card says "Reply with the selector only". So the protocol forbids declining and the eval
has never contained a question that should be declined. Of 23,796 predictions across every run,
33 (0.14%) contain any refusal language. The models invent because they were told to answer and
never penalised for answering wrongly where no answer exists -- that is a design gap, not a
model defect.

INEXPRESSIBILITY IS VERIFIED, NOT ASSUMED. Each category below needs a capability the card does
not grant AND the engine rejects. Probed on the pinned engine:

    .fn[lines>50]              ERROR malformed selector      -> no size/length
    .mod:has-count(.fn, 10)    ERROR unknown pseudo-class    -> no counting
    .class#Animal .fn .call    ERROR combinator chains of..  -> exactly two steps

One category I had planned was WRONG and is dropped: `.mod > .fn:first-child` RETURNS 3 NODES,
so position/ordering IS expressible. Guessing at a language's limits is how you build an
abstention suite that punishes correct answers.

CONTROLS MATTER AS MUCH AS CASES. Half the suite is answerable and verified against the engine,
because the failure mode of teaching abstention is over-refusal -- a model that declines
anything oddly worded is worse than one that always answers.
"""
import json, os, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#: (category, request) -- needs a capability the language lacks
CANNOT = [
 ("size", "functions longer than fifty lines"),
 ("size", "the biggest class in this codebase"),
 ("size", "any function whose body runs past one screen"),
 ("size", "short helpers, under five lines"),
 ("size", "which file has the most code in it"),
 ("count", "files that define more than ten functions"),
 ("count", "classes with at least a dozen methods"),
 ("count", "how many times is open called"),
 ("count", "modules importing fewer than three things"),
 ("count", "the function with the most call sites"),
 ("superlative", "the most-called function here"),
 ("superlative", "whichever class is referenced least"),
 ("superlative", "the deepest nested loop in the project"),
 ("history", "functions changed in the last week"),
 ("history", "whatever Ana wrote most recently"),
 ("history", "code that has not been touched in a year"),
 ("history", "functions added since the last release"),
 ("judgement", "the slow functions"),
 ("judgement", "badly named helpers"),
 ("judgement", "anything that looks thread-unsafe"),
 ("judgement", "the buggy parts of this module"),
 ("judgement", "functions that need refactoring"),
 ("judgement", "code a reviewer would complain about"),
 ("dataflow", "functions whose return value is never used"),
 ("dataflow", "variables assigned but never read"),
 ("dataflow", "where does the user_id value end up"),
 ("dataflow", "calls whose result is discarded"),
 ("three-step", "calls inside loops inside the methods of User"),
 ("three-step", "string literals in conditionals in test functions"),
 ("three-step", "imports inside functions inside classes"),
 ("runtime", "functions that allocate memory"),
 ("runtime", "code paths that can throw at runtime"),
 ("runtime", "functions that touch the network"),
]

#: (expected selector, request) -- verified expressible; these catch OVER-refusal
CAN = [
 (".fn[params=3]", "functions taking exactly three parameters"),
 (".fn:not(:has(.throw))", "functions that never raise"),
 (".comment + .fn", "a comment immediately followed by a function"),
 (".mod > .fn:first-child", "the first thing defined at the top of the file"),
 (".fn[name^=\"test_\"]", "functions whose name starts with test_"),
 (".call[receiver=\"self\"]", "methods invoked on self"),
 (".fn:not(:is-called)", "functions nothing ever calls"),
 (".class[name*=\"Test\"]", "classes with Test somewhere in the name"),
 (".fn:has(.loop)", "functions that loop over something"),
 (".fn:calls(print)", "functions whose own body calls print"),
 (".import ~ .var", "a variable declared after an import"),
 (".fn:has(.try)", "functions that guard against failure"),
 (".class .fn", "methods belonging to some class"),
 (".fn:typed", "functions that declare a return type"),
 (".call#open", "every call to open"),
 (".fn:not(:has(.call))", "functions that call nothing at all"),
 (".member", "attribute accesses"),
 (".fn:has(.comp)", "functions using a comprehension"),
]

def main():
    rows, i = [], 0
    for cat, nl in CANNOT:
        i += 1
        rows.append({"id": "ab-c%03d" % i, "tier": 5, "fixture": "ho-python-mindmeld",
                     "nl": nl, "paraphrases": [], "css": None, "answerable": False,
                     "category": cat, "tags": ["abstain", "never-train", "v0"]})
    for css, nl in CAN:
        i += 1
        rows.append({"id": "ab-a%03d" % i, "tier": 5, "fixture": "ho-python-mindmeld",
                     "nl": nl, "paraphrases": [], "css": css, "answerable": True,
                     "category": "control", "tags": ["abstain", "never-train", "v0"]})
    p = os.path.join(HERE, "abstain/pairs/candidates.jsonl")
    with open(p, "w") as fh:
        for r in rows: fh.write(json.dumps(r) + "\n")
    import collections
    print("%d requests -> %s" % (len(rows), p))
    print("  unanswerable: %d  %s" % (sum(1 for r in rows if not r["answerable"]),
          dict(collections.Counter(r["category"] for r in rows if not r["answerable"]))))
    print("  answerable  : %d (controls, verified expressible)" % sum(1 for r in rows if r["answerable"]))

if __name__ == "__main__":
    main()
