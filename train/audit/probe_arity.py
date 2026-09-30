"""Discover which zero-arg/attribute forms are usable, and with which VALUES.

The 9B's remaining errors on eval_t5 are three of one mistake: it invents parameterized
forms of zero-argument pseudo-classes -- `.fn:decorated(by="property")` for
`.fn[annotation*="property"]`, `.fn:typed(None)` for `.fn[signature="None"]`, and
`.fn#create_user::call` for `::callees`. The card is already right (attributes on lines
51-52, bare pseudo-classes on line 61); the model conflates the two.

`:typed(None)` EXECUTES rather than erroring, so nothing catches it -- the same
silent-acceptance trap as `:scope(X)`.

This pass finds, per fixture: the node counts for the bare forms, and which concrete
decorator names and return types actually occur. verify.py needs a reference in 1..50, so
counts matter as much as existence.
"""
import json, os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")
import verify as V

FX = ["py-lackpy", "py-blq", "py-pluckit", "py-umwelt"]
DECOS = ["property", "classmethod", "staticmethod", "dataclass", "cached_property",
         "abstractmethod", "override", "wraps", "lru_cache", "contextmanager"]
RETS  = ["None", "bool", "str", "int", "float", "bytes", "Path", "dict", "list"]

q = []
for fx in FX:
    q.append(("%s|bare|decorated" % fx, fx, ".fn:decorated"))
    q.append(("%s|bare|typed" % fx, fx, ".fn:typed"))
    q.append(("%s|bare|async" % fx, fx, ".fn:async"))
    q.append(("%s|bare|fn" % fx, fx, ".fn"))
    for d in DECOS:
        q.append(("%s|anno|%s" % (fx, d), fx, '.fn[annotation*="%s"]' % d))
    for r in RETS:
        q.append(("%s|sig|%s" % (fx, r), fx, '.fn[signature="%s"]' % r))
got = V.execute(q)

def n(k):
    r = got.get(k, {})
    return -1 if "error" in r else len(r["nodes"])

print("%-12s %8s %8s %8s %8s" % ("fixture", ".fn", ":decorated", ":typed", ":async"))
for fx in FX:
    print("%-12s %8d %8d %8d %8d" % (fx, n("%s|bare|fn"%fx), n("%s|bare|decorated"%fx),
                                     n("%s|bare|typed"%fx), n("%s|bare|async"%fx)))
print("\n=== [annotation*=\"X\"] counts (usable = 1..50) ===")
print("%-16s %s" % ("value", "  ".join("%-12s" % f for f in FX)))
for d in DECOS:
    row = ["%-12s" % (n("%s|anno|%s"%(f,d)) if n("%s|anno|%s"%(f,d))>=0 else "ERR") for f in FX]
    print("%-16s %s" % (d, "  ".join(row)))
print("\n=== [signature=\"X\"] counts ===")
for r in RETS:
    row = ["%-12s" % (n("%s|sig|%s"%(f,r)) if n("%s|sig|%s"%(f,r))>=0 else "ERR") for f in FX]
    print("%-16s %s" % (r, "  ".join(row)))
json.dump({k: n(k) for k in got}, open("workspace/arity_counts.json", "w"), indent=1)
