"""Contrastive pairs separating ZERO-ARGUMENT pseudo-classes from ATTRIBUTE selectors.

WHY. Three of the 9B's eight remaining errors on eval_t5 are one mistake: it invents a
parameterized form of a bare pseudo-class.

    want .fn[annotation*="property"]   got .fn:decorated(by="property")
    want .fn[signature="None"]         got .fn:typed(None)
    want .fn#create_user::callees      got .fn#create_user::call

The card is already correct -- attributes on lines 51-52, bare pseudo-classes on line 61 --
so this is not a card gap. And `.fn:typed(None)` EXECUTES instead of erroring, the same
silent-acceptance trap as `:scope(X)`, so nothing in the pipeline flags it. Fixing these
three takes the 9B from 110/118 (93.2%) to 113/118 (95.8%).

THE CONTRAST IS ANY-VS-WHICH. `:typed` asks whether a return type is declared at all;
`[signature="T"]` asks whether it is T. `:decorated` asks whether a decorator is present;
`[annotation*="X"]` asks whether it mentions X. Those are different questions with different
answers, so the engine gate can confirm each pair discriminates.

TEN PHRASINGS PER SIDE, not one. The previous batch (pseudo-d3) drew 152 pairs from six
templates, and two things followed: `--cap-template 8` admitted only 55 of them, because the
cap groups by (request template, selector shape); and the eval built from those templates
could not, on its own, distinguish learning from memorisation. Both are the same defect.
Phrasings here rotate by pair index so a fixture's pairs land in many template groups.

PYTHON IS HELD OUT SEPARATELY. pseudo-d3 gained +28-33 points on five non-Python languages
while REGRESSING Python by 11 points, and because the headline eval is Python-only it read as
a small loss. These forms are Python-centric (decorators, return annotations), so the split
here is by fixture: three fixtures train, one is held out entirely, and the trade -- if it
recurs -- is visible instead of averaged away.

    python3 train/audit/arity_pairs.py write
"""
import json, os, sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.join(HERE, "train/candidates/arity-a1.jsonl")

ANY_DECO = [
    "functions that carry a decorator at all", "any decorated function",
    "definitions that have a decorator, whichever one", "functions wrapped by any decorator",
    "every decorated definition here", "which functions have decorators?",
    "functions that are decorated, regardless of which decorator",
    "decorated definitions, no particular decorator",
    "functions bearing at least one decorator", "functions with something applied above them",
]
WHICH_DECO = [
    "functions decorated with %s", "functions whose decorator is %s",
    "definitions carrying the %s decorator", "functions marked %s",
    "where is %s applied as a decorator?", "the %s-decorated functions",
    "functions using %s above the def", "definitions whose decorator mentions %s",
    "which functions have %s on them?", "functions annotated %s",
]
ANY_TYPE = [
    "functions that declare a return type", "functions with a return annotation, any type",
    "definitions that state what they return", "which functions are return-annotated?",
    "functions carrying an explicit return type", "every function with a declared return",
    "typed functions, whatever the type", "functions that annotate their return value",
    "definitions with a return type declared", "functions whose return type is spelled out",
]
WHICH_TYPE = [
    "functions whose return type is %s", "functions declared to return %s",
    "functions annotated to return %s", "which functions return %s?",
    "definitions with return type %s", "functions that return %s per their signature",
    "the functions typed to give back %s", "functions whose signature says %s",
    "functions returning %s according to the annotation", "definitions declaring %s as the return",
]


def rotate(pool, i):
    """nl plus two paraphrases, all from the pool, none repeated within the pair."""
    k = len(pool)
    return [pool[i % k], pool[(i + 3) % k], pool[(i + 6) % k]]


def build(counts, fixtures, scope=None):
    """counts: {"<fx>|<kind>|<value>": n} from probe_arity. Only 1..50 can be a reference."""
    rows, i = [], 0
    ok = lambda key: 1 <= counts.get(key, -1) <= 50
    for fx in fixtures:
        pre = scope.get(fx, "") if scope else ""
        for kind, bare_sel, bare_pool, attr_fmt, which_pool, prefix in (
            ("decorated", ".fn:decorated", ANY_DECO, '.fn[annotation*="%s"]', WHICH_DECO, "anno"),
            ("typed", ".fn:typed", ANY_TYPE, '.fn[signature="%s"]', WHICH_TYPE, "sig"),
        ):
            if not ok("%s|bare|%s" % (fx, kind)):
                continue
            for val in sorted(v.split("|")[-1] for v in counts
                              if v.startswith("%s|%s|" % (fx, prefix)) and ok(v)):
                a_sel, b_sel = pre + bare_sel, pre + (attr_fmt % val)
                for side, sel, pool, other in (("a", a_sel, bare_pool, b_sel),
                                               ("b", b_sel, which_pool, a_sel)):
                    i += 1
                    texts = rotate(pool, i)
                    texts = [t % val if "%s" in t else t for t in texts]
                    rows.append({"id": "tr-python-t5-ar%04d%s" % (i, side), "tier": 5,
                                 "fixture": fx, "nl": texts[0], "paraphrases": texts[1:],
                                 "css": sel, "distractors": [other], "treeql": None,
                                 "tags": ["sitting_duck_supported", "arity-contrast", "v0"],
                                 "contrast": {"kind": kind + "-" + side, "against": other}})
    return rows


def main():
    counts = json.load(open(os.path.join(HERE, "workspace/arity_counts.json")))
    TRAIN_FX = ["py-lackpy", "py-blq", "py-pluckit"]
    HELD_FX = ["py-umwelt"]          # held out ENTIRELY: the Python trade must stay visible
    tr = build(counts, TRAIN_FX)
    ev = build(counts, HELD_FX)
    for name, rows in (("arity-a1", tr), ("arity-a1-held", ev)):
        p = os.path.join(HERE, "train/candidates/%s.jsonl" % name)
        with open(p, "w") as fh:
            for r in rows: fh.write(json.dumps(r) + "\n")
        import collections
        print("%-14s %4d candidates  %s" % (name, len(rows),
              dict(collections.Counter(r["contrast"]["kind"] for r in rows))))
        print("               distinct nl templates: %d" % len({r["nl"] for r in rows}))


if __name__ == "__main__":
    main()
