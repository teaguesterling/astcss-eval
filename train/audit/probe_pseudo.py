"""Probe every pseudo-class / pseudo-element the card teaches, on the PINNED engine.

Two questions, and the second is the one that decides fixture choice:

  1. Does the form execute, return nodes, and DIFFER from its bare form? `:scope(X)` is
     known to return 0 nodes always while never erroring, so "recognised" is not "works".
     :decorated, :async and :is-referenced have ZERO training coverage and may be traps too.

  2. What actually separates `::callees` from a descendant ` .call`? I told Teague a nested
     call would do it. oracle.py:722 documents ::callees as "named calls, nested functions
     INCLUDED", and descendant .call includes nested ones too -- so nesting should NOT
     discriminate on pinned (it does on main, which is the open upstream regression).
     The hypothesis to test is that UNNAMED/COMPUTED calls are what separate them.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")
import verify as V

FX = ["py-lackpy", "py-blq", "js-messe", "rs-magic", "go-rosetta"]

# (label, selector, bare form it must differ from)
FORMS = [
    ("has",           ".fn:has(.call)",            ".fn"),
    ("not",           ".fn:not(:has(.call))",      ".fn"),
    ("in-scope",      ".fn:in-scope(.class)",      ".fn"),
    ("scope-paren",   ".fn:scope(.class)",         ".fn"),
    ("scope-elem",    ".fn::scope",                ".fn"),
    ("is-called",     ".fn:is-called",             ".fn"),
    ("called-by",     ".call:called-by(.fn)",      ".call"),
    ("calls",         ".fn:calls(.call)",          ".fn"),
    ("typed",         ".fn:typed",                 ".fn"),
    ("exported",      ".fn:exported",              ".fn"),
    ("decorated",     ".fn:decorated",             ".fn"),
    ("async",         ".fn:async",                 ".fn"),
    ("is-referenced", ".fn:is-referenced",         ".fn"),
    ("callees",       ".fn::callees",              ".fn .call"),
    ("callers",       ".fn::callers",              ".fn"),
]

q, want = [], {}
for fx in FX:
    for label, sel, bare in FORMS:
        for tag, s in (("f", sel), ("b", bare)):
            qid = "%s|%s|%s" % (fx, label, tag)
            q.append((qid, fx, s)); want[qid] = s
print("engine:", json.dumps(V.engine_identity()["macros"]), file=sys.stderr)
got = V.execute(q)

print("%-14s %-13s %-22s %s" % ("form", "fixture", "form -> nodes", "vs bare"))
agg = {}
for label, sel, bare in FORMS:
    for fx in FX:
        f = got["%s|%s|f" % (fx, label)]; b = got["%s|%s|b" % (fx, label)]
        if "error" in f:
            verdict = "ERROR: " + f["error"][:40]
        elif "error" in b:
            verdict = "bare errors"
        elif not f["nodes"]:
            verdict = "ZERO NODES (trap)"
        elif f["nodes"] == b["nodes"]:
            verdict = "VACUOUS: same as %s" % bare
        else:
            verdict = "discriminates (%d vs %d)" % (len(f["nodes"]), len(b["nodes"]))
        agg.setdefault(label, []).append(verdict.split(":")[0].split(" (")[0])
        print("%-14s %-13s %-22s %s" % (label, fx, sel[:22], verdict))
print()
print("=== summary across %d fixtures ===" % len(FX))
for label, vs in agg.items():
    import collections
    print("%-14s %s" % (label, dict(collections.Counter(vs))))
