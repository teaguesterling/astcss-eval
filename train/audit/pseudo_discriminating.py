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

OUT = os.path.join(HERE, "train/candidates/pseudo-d3.jsonl")
INV = os.path.join(HERE, "train/audit/inventories/%s.json")

# fixture -> (language word for the NL, forms that discriminate there)
# Every fixture with functions. The per-fixture form sets of v1 are gone: the ENGINE gate
# decides what discriminates, and hardcoding my expectation was just a slower way of being
# wrong. `:calls(X)` IS dropped -- it tied `:has(.call#X)` on 32 of 32 candidates across five
# fixtures, so on the pinned engine it is not call-graph-resolved and there is no distinction
# to teach. Keeping it would spend the gate's budget re-proving that.
FIXTURES = {
    "c-duckhts": "c", "cpp-duck-hunt": "cpp", "cpp-duckdb-mcp": "cpp",
    "cpp-duckdb-yaml": "cpp", "go-rosetta": "go", "java-rosetta": "java",
    "js-messe": "javascript", "js-rosetta": "javascript", "py-blq": "python",
    "py-lackpy": "python", "py-pluckit": "python", "py-umwelt": "python",
    "rs-cosmic-goo": "rust", "rs-magic": "rust", "rs-rosetta": "rust",
    "sh-homelab": "bash", "sh-mixed": "bash",
}

#: A bare-class contrast (`.fn:typed` vs `.fn`) needs `.fn` itself inside verify's 1..50
#: bound, or the pair is rejected on node count before its distractor is ever consulted --
#: which is how 38 of v1's 140 candidates died. Only these fixtures qualify.
SMALL_FN = {"go-rosetta": 38, "java-rosetta": 70, "rs-rosetta": 43,
            "sh-homelab": 12, "sh-mixed": 8}



def names(fixture, key):
    raw = json.load(open(INV % fixture))[key]
    return {m.group(1): int(m.group(2)) for m in re.finditer(r'([\w$]+)\((\d+)\)', raw)}


def targets(fixture, k=20):
    """Two pools, because the forms need different things of a name -- and the inventories
    are TRUNCATED to the 60 commonest names, so intersecting two truncated lists starved v2
    to one target on some fixtures (c-duckhts: 24 uniquely-defined functions, 2 of them also
    in the call list).

      subject   defined exactly ONCE, so `.fn#name` has one unambiguous subject. Enough for
                ::callees and :called-by(), which ask what the function calls -- nothing
                requires it to be called itself.
      called    also appears as a call, which ::callers needs: a function nobody calls has
                no callers, the reference returns 0 nodes, and verify rejects it on the lower
                bound before the distractor is consulted.
    """
    fns, calls = names(fixture, "fn_names"), names(fixture, "call_names")
    once = [n for n in fns if fns[n] == 1 and not n.startswith("__")]
    subject = sorted(once, key=lambda n: -calls.get(n, 0))[:k]
    called = [n for n in subject if 2 <= calls.get(n, 0) <= 40][:k]
    return subject, called


# Each entry: the two sides of one contrast. Both get written as training rows, each with the
# other as its distractor, so whichever the model answers it has committed to a distinction.
# The English is the load-bearing part: "makes, per the call graph" vs "written inside".
def contrasts(fx, lang, name, needs_called=True):
    """needs_called: include the forms that require the name to be CALLED (::callers)."""
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
    if needs_called:
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
    for fx, lang in sorted(FIXTURES.items()):
        subject, called = targets(fx)
        pool = [(k, a, b) for name in subject
                for k, a, b in contrasts(fx, lang, name, needs_called=(name in called))]
        # The bare-class contrast only where `.fn` fits the node bound (see SMALL_FN).
        if fx in SMALL_FN and SMALL_FN[fx] <= 50:
            pool += unary(fx, lang)
        elif fx in SMALL_FN:
            pool += [t for t in unary(fx, lang) if t[0] == "is_called"]
        for kind, (css_a, nl_a), (css_b, nl_b) in pool:
            for side, (css, nl, other) in (("a", (css_a, nl_a, css_b)), ("b", (css_b, nl_b, css_a))):
                n += 1
                rows.append({"id": "tr-%s-t5-pd%04d%s" % (lang, n, side),
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
    sels = {(r["fixture"], r["css"]) for r in rows}
    print("distinct (fixture, selector) engine calls: %d" % len(sels))


if __name__ == "__main__":
    main()
