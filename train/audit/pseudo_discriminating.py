"""Contrastive training pairs for the call-graph pseudo-classes and pseudo-elements.

WHY THIS BATCH EXISTS. The 120-pair eval_t5 cannot tell these forms from their syntactic
lookalikes. Mining all seven rebase120 runs for predictions that earned exec_match with a
DIFFERENT string turned up 24 pseudo-form pairs where a purely syntactic answer scores full
credit -- 8 `:called-by(X)` answered `.fn#X .call`, 4 `::callees` answered `.fn#X .call`,
3 `::callers` answered `:has(.call#X)`, 5 `:calls(X)` answered `:has(.call#X)`, 3 `:scope`,
1 `:is-called`. t5-p55 was not special; it was the one that happened to be noticed.

DISTRACTORS ARE A GATE, NOT A SIGNAL. The model only ever sees card + NL -> css, so a
declared distractor teaches it nothing directly -- verify.py just refuses the pair when the
distractor returns the reference's node set. What teaches the distinction is a MINIMAL PAIR:
on a fixture where the two selectors genuinely differ, emit BOTH as training rows, each
carrying the other as its distractor, with English a careful reader maps to one and not the
other. If no such English can be written, the pair teaches nothing and is dropped.

FORMS INCLUDED, and why these. Probed on the pinned engine across five fixtures
(workspace/probe_pseudo.py):

    ::callees     discriminates from `.fn .call` on 4/5 fixtures (VACUOUS on py-blq)
    ::callers     5/5        :is-called     5/5        :calls()   5/5
    :called-by()  3/5 (VACUOUS on rs-magic, go-rosetta: every call sits in a function)
    :typed        4/5 (VACUOUS on js-messe)            :exported  5/5

EXCLUDED, and why -- these are the finding, not an oversight:

    :in-scope(.class)  ERRORS on all 5 ("ast_select: unknown"): it requires a NAMED argument.
    :scope(.class)     VACUOUS on all 5 -- returns exactly `.fn`, the constraint ignored.
                       With a named argument it is not vacuous (`.fn:scope(.class#Cat)` is 3
                       nodes on py-variety, not 84) and not empty, so the earlier conclusion
                       that `:scope(X)` "always returns 0" was wrong. Its actual semantics
                       are still not pinned down, so no pair here depends on them.
    :decorated/:async  ZERO NODES on the 3 non-Python fixtures. Python-only, not traps.

Nesting is NOT what separates `::callees` from a descendant `.call`: oracle.py:722 documents
::callees as including nested functions, and so does the descendant form. They part company
over calls the call graph resolves differently, which is why the gate -- not a guess about
fixtures -- decides every pair here.

    python3 train/audit/pseudo_discriminating.py write
    python3 pilot.py train/candidates/pseudo-d1.jsonl pseudo-d1 train --paraphrases=distinct
"""
import json, os, re, sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, HERE)

OUT = os.path.join(HERE, "train/candidates/pseudo-d1.jsonl")
INV = os.path.join(HERE, "train/audit/inventories/%s.json")

# fixture -> (language word for the NL, forms that discriminate there)
FIXTURES = {
    "py-lackpy":  ("python",     {"callees", "callers", "called_by", "calls", "is_called", "typed", "exported"}),
    "py-blq":     ("python",     {"callers", "called_by", "calls", "is_called", "typed", "exported"}),
    "js-messe":   ("javascript", {"callees", "callers", "called_by", "calls", "is_called", "exported"}),
    "rs-magic":   ("rust",       {"callees", "callers", "calls", "is_called", "typed", "exported"}),
    "go-rosetta": ("go",         {"callees", "callers", "calls", "is_called", "typed", "exported"}),
}


def names(fixture, key):
    raw = json.load(open(INV % fixture))[key]
    return {m.group(1): int(m.group(2)) for m in re.finditer(r'([\w$]+)\((\d+)\)', raw)}


def targets(fixture, k=6):
    """Names defined ONCE as a function and called a handful of times: a call-graph question
    about them has one unambiguous subject, and enough call sites for the graph to matter."""
    fns, calls = names(fixture, "fn_names"), names(fixture, "call_names")
    out = [n for n, c in sorted(calls.items(), key=lambda kv: -kv[1])
           if fns.get(n) == 1 and 2 <= c <= 20 and not n.startswith("__")]
    return out[:k]


# Each entry: the two sides of one contrast. Both get written as training rows, each with the
# other as its distractor, so whichever the model answers it has committed to a distinction.
# The English is the load-bearing part: "makes, per the call graph" vs "written inside".
def contrasts(fx, lang, name):
    c = []
    c.append(("callees",
              (".fn#%s::callees" % name,
               ["the calls %s makes, resolved through the call graph" % name,
                "what does %s end up calling?" % name,
                "%s's callees" % name]),
              (".fn#%s .call" % name,
               ["every call expression written inside the body of %s" % name,
                "the call syntax that appears textually within %s" % name,
                "call nodes nested under %s" % name])))
    c.append(("callers",
              (".fn#%s::callers" % name,
               ["the functions that call %s, per the call graph" % name,
                "who calls %s?" % name,
                "%s's callers" % name]),
              (".fn:has(.call#%s)" % name,
               ["functions whose body literally contains a call written %s" % name,
                "functions with %s appearing as a call inside them" % name,
                "any function containing the call syntax %s" % name])))
    c.append(("called_by",
              (".call:called-by(%s)" % name,
               ["the calls %s makes, per the call graph" % name,
                "call sites attributed to %s by the call graph" % name,
                "calls whose caller is %s" % name]),
              (".fn#%s .call" % name,
               ["call expressions written inside %s" % name,
                "the calls appearing textually in %s's body" % name,
                "call nodes under the %s definition" % name])))
    c.append(("calls",
              (".fn:calls(%s)" % name,
               ["functions that call %s, following the call graph" % name,
                "call-graph callers of %s" % name,
                "which functions reach %s?" % name]),
              (".fn:has(.call#%s)" % name,
               ["functions containing a literal call to %s" % name,
                "functions where %s appears written as a call" % name,
                "functions with the call syntax %s inside" % name])))
    return c


def unary(fx, lang):
    """Forms with no argument: the contrast is against the bare class, which is the answer a
    model gives when it drops the modifier -- the single commonest failure in the mined set."""
    return [
        ("is_called",
         (".fn:is-called",
          ["functions that are called from somewhere in this %s code" % lang,
           "which functions actually get invoked?",
           "functions reached by at least one call"]),
         (".fn:has(.call)",
          ["functions that themselves contain a call",
           "functions making at least one call of their own",
           "functions with a call inside them"])),
        ("typed",
         (".fn:typed",
          ["functions carrying type annotations",
           "the explicitly typed functions",
           "functions with declared types"]),
         (".fn",
          ["every function in this %s code" % lang,
           "all the function definitions",
           "list the functions"])),
        ("exported",
         (".fn:exported",
          ["functions this %s code exports" % lang,
           "the publicly exported functions",
           "functions visible outside their module"]),
         (".fn",
          ["every function defined here",
           "all function definitions in the %s sources" % lang,
           "the complete list of functions"])),
    ]


def main():
    rows, n = [], 0
    for fx, (lang, ok) in sorted(FIXTURES.items()):
        tg = targets(fx)
        pool = [(k, a, b) for name in tg for k, a, b in contrasts(fx, lang, name)]
        pool += unary(fx, lang)
        for kind, (css_a, nl_a), (css_b, nl_b) in pool:
            if kind not in ok:
                continue
            for side, (css, nl, other) in (("a", (css_a, nl_a, css_b)), ("b", (css_b, nl_b, css_a))):
                n += 1
                rows.append({"id": "tr-pd-%s-%04d%s" % (fx.split("-")[0], n, side),
                             "tier": 5, "fixture": fx, "nl": nl[0], "paraphrases": nl[1:],
                             "css": css, "distractors": [other], "treeql": None,
                             "tags": ["sitting_duck_supported", "pseudo-discriminating", "v0"],
                             "contrast": {"kind": kind, "against": other}})
    with open(OUT, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    import collections
    print("wrote %d candidate rows -> %s" % (len(rows), OUT))
    print("by fixture: %s" % dict(collections.Counter(r["fixture"] for r in rows)))
    print("by contrast: %s" % dict(collections.Counter(r["contrast"]["kind"] for r in rows)))


if __name__ == "__main__":
    main()
