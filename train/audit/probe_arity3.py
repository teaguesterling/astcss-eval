"""Are `:decorated(by=...)` and `:typed(X)` real forms, or silently-accepted non-forms?

The card fix told the 9B verbatim that both are wrong and named the replacements. It kept
writing them. And on t5-p31 `.class .fn:decorated(by="method")` EXEC-MATCHED. So before
calling these model errors, ask the engine what they actually do -- compared with the bare
form, the attribute form, and a deliberately nonsense argument.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")
import verify as V

FX = "py-variety"     # the eval fixture the failing pairs live on
CASES = [
    ("bare decorated",        ".fn:decorated"),
    ("attr property",         '.fn[annotation*="property"]'),
    ("paren by=property",     '.fn:decorated(by="property")'),
    ("paren by=nonsense",     '.fn:decorated(by="zzzznotathing")'),
    ("paren bare-arg",        '.fn:decorated(property)'),
    ("bare typed",            ".fn:typed"),
    ("attr signature None",   '.fn[signature="None"]'),
    ("paren typed(None)",     ".fn:typed(None)"),
    ("paren typed(nonsense)", ".fn:typed(Zzzznotatype)"),
    ("attr annotation cm",    '.fn[annotation*="classmethod"]'),
    ("scoped .class .fn dec", '.class .fn:decorated(by="method")'),
    ("scoped attr cm",        '.class .fn[annotation*="classmethod"]'),
]
got = V.execute([(l, FX, s) for l, s in CASES])
res = {}
print("%-24s %-38s %s" % ("label", "selector", "result"))
for l, s in CASES:
    r = got[l]
    if "error" in r:
        out = "ERROR: " + r["error"][:44]
    else:
        out = "%d nodes" % len(r["nodes"]); res[l] = r["nodes"]
    print("%-24s %-38s %s" % (l, s, out))
print("\n=== do the paren forms equal anything? ===")
def cmp(a, b):
    if a not in res or b not in res: return "n/a"
    return "IDENTICAL" if res[a] == res[b] else "different (%d vs %d)" % (len(res[a]), len(res[b]))
for a, b in (("paren by=property", "attr property"), ("paren by=property", "bare decorated"),
             ("paren by=nonsense", "bare decorated"), ("paren by=nonsense", "paren by=property"),
             ("paren typed(None)", "attr signature None"), ("paren typed(None)", "bare typed"),
             ("paren typed(nonsense)", "bare typed"), ("paren typed(nonsense)", "paren typed(None)"),
             ("scoped .class .fn dec", "scoped attr cm")):
    print("  %-26s vs %-24s -> %s" % (a, b, cmp(a, b)))
