"""Selector-first training pairs across tiers 1-5, checked by oracle.py.

The selector-first pilot (workspace/sfgen.py) showed the approach works: 343 of 352
candidates passed verification, with Python predictions identical to the engine. This is
its successor for the larger suite: every language, tier 5 (relational and compound
selectors), and documented semantics for the engine features with filed defects.

  enumerate  compose selectors per fixture from the engine's node table (oracle.Tree),
             keep those in bounds, load-bearing, new to training and not an eval answer;
             tier-5 families: chained constraints, scoped steps, receivers, call graph,
             references and exports, :scope(selector), modifiers and annotations
  word       a device model writes a typed request, a spoken version and a question from
             the selector, a plain-English gloss and two matched source lines
  verify     oracle.verify_batch: gates on the documented node set; the engine's answer
             sorts accepted from pending_engine:<issue>
  back       a second device model translates each wording back to a selector; scored
             by the documented node set (oracle.parse + Tree.select)
  report

usage: python3 tune/gen_pairs.py STAGE --out DIR [--fixtures a,b] [--per-fixture N] [--batch ID]
"""
import argparse
import collections
import copy
import glob
import json
import os
import random
import re
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import oracle as O  # noqa: E402
import pilot  # noqa: E402
import verify as V  # noqa: E402
from oracle import C, P, S, render, tier  # noqa: E402

WORD_MODEL = "google/gemma-4-26B-A4B-it"
BACK_MODEL = "Qwen/Qwen3.6-27B"
LANG_BY_PREFIX = {"py": "python", "rs": "rust", "js": "javascript", "go": "go", "java": "java",
                  "c": "c", "cpp": "cpp", "sh": "bash", "sql": "sql"}
# Classes the language packets mark unreliable (train/packets/<lang>.md, "Notes for <lang>").
DENY = {"python": set(), "rust": {".if", ".member", ".try", ".catch", ".throw"}, "javascript": {".import"},
        "c": {".if", ".import", ".member"}, "cpp": {".fn", ".if", ".import", ".member"}, "go": {".mod"},
        "java": {".if", ".catch", ".member"}, "bash": {".call", ".member", ".class", ".import", ".jump", ".try"},
        "sql": {".fn", ".if", ".loop", ".jump", ".member", ".import"}}
UNNAMED_TYPES = {"bash": {"command"}}          # #140: names don't bind
FN_LIKE = {".fn", "function_definition", "function_item", "method_declaration", "method_definition",
           "function_declaration", "arrow_function"}
OPS = [" ", ">", "~", "+"]
QUOTA = {"t1": 0.03, "name": 0.05, "attr": 0.07, "params": 0.03, "t3": 0.12, "t4": 0.15,
         "chain": 0.12, "scoped": 0.10, "receiver": 0.08, "graph": 0.10, "refs": 0.06, "scope": 0.05, "mods": 0.04}
IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{2,39}$")
NOUNS = {
    ".fn": ("functions", "function"), ".class": ("classes", "class"), ".var": ("variable definitions", "variable definition"),
    ".call": ("calls", "call"), ".member": ("attribute accesses", "attribute access"),
    ".import": ("imports", "import"), ".if": ("conditionals", "conditional"), ".loop": ("loops", "loop"),
    ".jump": ("return, break or continue statements", "return, break or continue statement"),
    ".try": ("try blocks", "try block"), ".catch": ("exception handlers", "exception handler"),
    ".throw": ("raise or throw statements", "raise or throw statement"), ".comp": ("comprehensions", "comprehension"),
    ".mod": ("files", "file"),
}


def lang_of(fx):
    return LANG_BY_PREFIX[fx.split("-")[0]]


def card_types(lang):
    card = open(os.path.join(HERE, "train", "cards", "card_%s.md" % lang)).read()
    m = re.search(r"NODE TYPES[^\n]*\n(.*?)\n\s*\n", card, re.S)
    return sorted(set(re.findall(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b", m.group(1)))) if m else []


def shape(css):
    s = re.sub(r'\[(\w+)([\^$*]?)="[^"]*"\]', r"[\1\2=_]", css)
    s = re.sub(r"\[params=\d+\]", "[params=_]", s)
    s = re.sub(r":(calls|called-by)\([^)]*\)", r":\1(_)", s)
    return re.sub(r"#[A-Za-z0-9_]+", "#_", s)


def log(out, msg):
    line = "%s %s" % (time.strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "gen.log"), "a") as fh:
        fh.write(line + "\n")


# ---------------------------------------------------------------- glosses

def noun(sel, lang, plural=True):
    if sel == ".class" and lang == "rust":
        return "structs, enums, traits or impls" if plural else "struct, enum, trait or impl"
    if sel in NOUNS:
        return NOUNS[sel][0 if plural else 1]
    w = sel.replace("_", " ")
    return w + "s" if plural else w


def article(p):
    return ("an " if p[:1].lower() in "aeiou" else "a ") + p


def gloss_pseudo(p, lang):
    k, a = p["kind"], p.get("arg")
    if k == "has":
        if a.get("name") is not None and not a.get("attrs") and not a.get("pseudos"):
            return "contain %s" % ("a call to %s" % a["name"] if a["sel"] == ".call"
                                   else article("%s named %s" % (noun(a["sel"], lang, False), a["name"])))
        return "contain at least one %s" % gloss_step(a, lang, False)
    if k == "not-has":
        return "contain no %s" % gloss_step(a, lang)
    if k == "not":
        inner = {"is-called": "are never called in their file", "is-referenced": "are never referenced in their file",
                 "decorated": "have no decorator", "async": "are not async", "typed": "declare no return type",
                 "exported": "are not public at module level"}.get(a["kind"])
        return inner or "do not " + gloss_pseudo(a, lang)
    if k == "calls":
        return "call %s from their own body (not only from a nested function)" % a
    if k == "called-by":
        return "are made directly inside the function %s" % a if a else "are made inside a function"
    if k == "is-called":
        return "are called somewhere in their file"
    if k == "is-referenced":
        return "are referenced somewhere in their file"
    if k == "exported":
        return "are public at module level"
    if k == "scope":
        if isinstance(a, dict):
            return "sit directly in %s (the nearest enclosing %s)" % (gloss_step(a, lang, False, the=True),
                                                                        noun(a["sel"], lang, False))
        return "sit inside %s" % article(a.replace("_", " "))
    return {"decorated": "have a decorator", "async": "are async", "typed": "declare a return type"}[k]


def gloss_step(st, lang, plural=True, the=False):
    base = noun(st["sel"], lang, plural)
    if st.get("name") is not None:
        s = ("the %s %s" % (noun(st["sel"], lang, False), st["name"])) if the or not plural else "%s named %s" % (base, st["name"])
    else:
        s = base
    for attr, op, val in st.get("attrs") or []:
        verb = {"=": "is", "^=": "starts with", "$=": "ends with", "*=": "contains"}[op]
        s += {"name": ' whose name %s "%s"' % (verb, val),
              "receiver": " made on %s" % val if op == "=" else ' made on an object whose name %s "%s"' % (verb, val),
              "signature": ' whose return type %s "%s"' % (verb, val),
              "annotation": ' whose decorator %s "%s"' % ("is" if op == "=" else "mentions", val),
              "params": " with exactly %s parameter%s" % (val, "" if str(val) == "1" else "s")}[attr]
    ps = st.get("pseudos") or []
    if ps:
        s += " that " + " and ".join(gloss_pseudo(p, lang) for p in ps)
    return s


def gloss(c, lang):
    if len(c["steps"]) == 1:
        return gloss_step(c["steps"][0], lang)
    a, b = c["steps"]
    ga = article(gloss_step(a, lang, False)) if a.get("name") is None else gloss_step(a, lang, False, the=True)
    gb = gloss_step(b, lang)
    return {" ": "%s anywhere inside %s", ">": "%s that are direct children of %s",
            "~": "%s that come later than %s at the same nesting level",
            "+": "%s that come immediately after %s at the same nesting level"}[c["op"]] % (gb, ga)


# ---------------------------------------------------------------- enumeration

def fragments(name):
    lead = re.match(r"^_*", name).group(0)
    parts = name.strip("_").split("_")
    out = []
    if len(parts) >= 2:
        out += [("^=", lead + parts[0] + "_"), ("$=", "_" + parts[-1])] + [("*=", p) for p in parts[1:-1]]
    else:
        toks = re.findall(r"[A-Z]?[a-z0-9]+|[A-Z]+(?![a-z])", name)
        if len(toks) >= 2:
            out += [("^=", lead + toks[0]), ("$=", toks[-1])] + [("*=", t) for t in toks[1:-1]]
    return [(op, v) for op, v in out if len(v.strip("_")) >= 3 and v != name]


class Enumerator:
    def __init__(self, tree, lang, rng, train_shapes, taken, eval_css):
        self.t, self.lang, self.rng = tree, lang, rng
        self.train_shapes, self.taken, self.eval_css = train_shapes, taken, eval_css
        n = tree.node
        self.classes = [s for s in O.CLASSES if tree.atoms.get(s) and s not in DENY[lang]]
        self.types = [s for s in card_types(lang) if tree.by_type.get(s)]
        self.steps = self.classes + self.types
        unnamed = UNNAMED_TYPES.get(lang, set())
        self.names = {}
        for s in (".fn", ".class", ".call", ".var", ".member"):
            if s in self.classes:
                cnt = collections.Counter(n[k]["name"] for k in tree.atoms[s] if n[k]["name"] and IDENT.match(n[k]["name"]))
                if cnt:
                    self.names[s] = cnt
        for s in self.types:
            if s in unnamed:
                continue
            cnt = collections.Counter(n[k]["name"] for k in tree.by_type[s] if n[k]["name"] and IDENT.match(n[k]["name"]))
            if len(cnt) >= 3 and s in FN_LIKE | {"class_definition", "struct_item", "impl_item", "class_declaration",
                                                  "invocation", "command_name"}:
                self.names[s] = cnt
        calls = tree.atoms.get(".call", set()) if ".call" in self.classes else set()
        self.receivers = collections.Counter(r for r in (tree.receiver(k) for k in calls) if r and IDENT.match(r))
        self.call_names = collections.Counter(n[k]["name"] for k in calls if n[k]["name"] and IDENT.match(n[k]["name"]))
        self.fn_sel = ".fn" if ".fn" in self.classes else next((s for s in self.types if s in FN_LIKE), None)
        fns = tree.base(self.fn_sel) if self.fn_sel else set()
        self.fn_names = collections.Counter(n[k]["name"] for k in fns if n[k]["name"] and IDENT.match(n[k]["name"]))
        self.params = collections.Counter(n[k]["nparams"] for k in fns)
        self.decorators = collections.Counter()
        self.signatures = collections.Counter()
        for k in fns:
            for d in re.findall(r"@([A-Za-z_][\w.]*)", n[k]["annotations"] or ""):
                self.decorators[d.split(".")[-1]] += 1
            sig = n[k]["signature_type"]
            if sig and IDENT.match(sig):
                self.signatures[sig] += 1
        self.class_sel = ".class" if ".class" in self.classes else None
        cls = tree.base(self.class_sel) if self.class_sel else set()
        self.class_names = collections.Counter(n[k]["name"] for k in cls if n[k]["name"] and IDENT.match(n[k]["name"]))

    # -- small helpers
    def pick(self, counter, limit=50):
        opts = [k for k, v in counter.items() if v <= limit]
        return self.rng.choice(opts) if opts else None

    def any_step(self):
        return S(self.rng.choice(self.steps))

    def inner_step(self, p_name=0.4):
        sel = self.rng.choice(self.steps)
        st = S(sel)
        if sel in self.names and self.rng.random() < p_name:
            st["name"] = self.pick(self.names[sel])
        return st

    def call_step(self):
        st = S(".call") if ".call" in self.classes else None
        if st and self.call_names:
            st["name"] = self.pick(self.call_names)
        return st

    def has(self, neg=None):
        neg = self.rng.random() < 0.5 if neg is None else neg
        inner = self.call_step() if (self.rng.random() < 0.45 and ".call" in self.classes) else self.inner_step()
        return P("not-has" if neg else "has", inner) if inner else None

    def target(self):
        r = self.rng.random()
        if self.fn_sel and r < 0.55:
            return S(self.fn_sel)
        if self.class_sel and r < 0.7:
            return S(self.class_sel)
        return self.any_step()

    # -- families
    def propose(self, fam):
        r, rng = self.rng, self.rng
        if fam == "t1":
            return C(self.any_step())
        if fam in ("name", "attr"):
            if not self.names:
                return None
            sel = rng.choice(list(self.names))
            if fam == "name":
                nm = self.pick(self.names[sel])
                return C(S(sel, nm)) if nm else None
            fr = fragments(rng.choice(list(self.names[sel])))
            if not fr:
                return None
            op, v = rng.choice(fr)
            return C(S(sel, attrs=[["name", op, v]]))
        if fam == "params":
            if not self.fn_sel or not self.params:
                return None
            return C(S(self.fn_sel, attrs=[["params", "=", rng.choice(list(self.params))]]))
        if fam == "t3":
            a = self.inner_step(0.35)
            b = self.inner_step(0.2)
            return C(a, b, op=rng.choice(OPS))
        if fam == "t4":
            p = self.has()
            return C(S(self.target()["sel"], pseudos=[p])) if p else None
        if fam == "chain":
            p1, p2 = self.has(), self.has()
            if not p1 or not p2 or O.rstep(p1["arg"]) == O.rstep(p2["arg"]):
                return None
            return C(S(self.target()["sel"], pseudos=[p1, p2]))
        if fam == "scoped":
            outer_pool = [(s, c) for s, c in ((self.class_sel, self.class_names), (self.fn_sel, self.fn_names)) if s and c]
            if not outer_pool:
                return None
            osel, onames = rng.choice(outer_pool)
            outer = S(osel, self.pick(onames, limit=5))
            choice = rng.random()
            if choice < 0.4:
                p = self.has()
                inner = S(self.target()["sel"], pseudos=[p]) if p else None
            elif choice < 0.6 and self.receivers and ".call" in self.classes:
                inner = S(".call", attrs=[["receiver", "=", self.pick(self.receivers)]])
            elif choice < 0.8 and self.fn_sel:
                inner = S(self.fn_sel, pseudos=[rng.choice([P("decorated"), P("not", P("is-called")), P("is-called")])])
            else:
                inner = self.inner_step(0.3)
                if inner["name"] is None:
                    return None
            return C(outer, inner, op=rng.choice([" ", " ", ">"])) if inner else None
        if fam == "receiver":
            if not self.receivers or ".call" not in self.classes:
                return None
            rv = self.pick(self.receivers)
            choice = rng.random()
            if choice < 0.35:
                return C(S(".call", attrs=[["receiver", "=", rv]]))
            if choice < 0.6 and self.call_names:
                return C(S(".call", self.pick(self.call_names), attrs=[["receiver", "=", rv]]))
            inner = S(".call", attrs=[["receiver", "=", rv]])
            if rng.random() < 0.4 and self.call_names:
                inner["name"] = self.pick(self.call_names)
            ps = [P("has", inner)]
            if rng.random() < 0.4:
                extra = self.has(neg=True)
                if extra:
                    ps.append(extra)
            return C(S(self.target()["sel"], pseudos=ps))
        if fam == "graph":
            if not self.fn_sel:
                return None
            choice = rng.random()
            if choice < 0.35 and self.call_names:
                ps = [P("calls", self.pick(self.call_names))]
                if rng.random() < 0.4:
                    extra = self.has(neg=True)
                    if extra:
                        ps.append(extra)
                return C(S(self.fn_sel, pseudos=ps))
            if choice < 0.6 and self.fn_names and ".call" in self.classes:
                st = S(".call", pseudos=[P("called-by", self.pick(self.fn_names, limit=3))])
                if rng.random() < 0.3 and self.call_names:
                    st["name"] = self.pick(self.call_names)
                return C(st)
            ps = [rng.choice([P("is-called"), P("not", P("is-called"))])]
            if rng.random() < 0.4:
                extra = self.has()
                if extra:
                    ps.append(extra)
            return C(S(self.fn_sel, pseudos=ps))
        if fam == "refs":
            tgt = rng.choice([s for s in (self.fn_sel, self.class_sel, ".var" if ".var" in self.classes else None) if s])
            ps = [rng.choice([P("is-referenced"), P("not", P("is-referenced")), P("exported")])]
            if ps[0]["kind"] == "exported" and rng.random() < 0.4:
                ps.append(rng.choice([P("not", P("is-called")), P("is-called")]))
            return C(S(tgt, pseudos=ps))
        if fam == "scope":
            pools = [(s, c) for s, c in ((self.class_sel, self.class_names), (self.fn_sel, self.fn_names)) if s and c]
            if not pools:
                return None
            osel, onames = rng.choice(pools)
            arg = S(osel, self.pick(onames, limit=3))
            tgt = rng.choice([s for s in (".call" if ".call" in self.classes else None, self.fn_sel,
                                          ".var" if ".var" in self.classes else None, ".loop" if ".loop" in self.classes else None) if s])
            st = S(tgt, pseudos=[P("scope", arg)])
            if tgt == ".call" and rng.random() < 0.4 and self.call_names:
                st["name"] = self.pick(self.call_names)
            return C(st)
        if fam == "mods":
            if not self.fn_sel:
                return None
            choice = rng.random()
            if choice < 0.25 and self.decorators:
                return C(S(self.fn_sel, attrs=[["annotation", "*=", self.pick(self.decorators)]]))
            if choice < 0.4 and self.signatures:
                return C(S(self.fn_sel, attrs=[["signature", "=", self.pick(self.signatures)]]))
            ps = [rng.choice([P("decorated"), P("not", P("decorated")), P("async"), P("typed"), P("not", P("typed"))])]
            if rng.random() < 0.5:
                extra = self.has()
                if extra:
                    ps.append(extra)
            return C(S(self.fn_sel, pseudos=ps))
        raise ValueError(fam)

    # -- near misses
    def distractors(self, c, ref):
        rng, alts = self.rng, []
        lst = len(c["steps"]) - 1
        st = c["steps"][lst]
        for j, p in enumerate(st.get("pseudos") or []):
            swap = {"has": "not-has", "not-has": "has"}.get(p["kind"])
            if swap:
                x = copy.deepcopy(c)
                x["steps"][lst]["pseudos"][j]["kind"] = swap
                alts.append(x)
            if p["kind"] == "not":
                x = copy.deepcopy(c)
                x["steps"][lst]["pseudos"][j] = p["arg"]
                alts.append(x)
            elif p["kind"] in ("is-called", "is-referenced", "decorated", "typed", "async", "exported"):
                x = copy.deepcopy(c)
                x["steps"][lst]["pseudos"][j] = P("not", p)
                alts.append(x)
            if p["kind"] == "calls" and p["arg"]:
                x = copy.deepcopy(c)
                x["steps"][lst]["pseudos"][j] = P("has", S(".call", p["arg"]))
                alts.append(x)
            if p["kind"] in ("has", "not-has") and p["arg"].get("name") and p["arg"]["sel"] == ".call" and self.call_names:
                other = self.pick(self.call_names)
                if other != p["arg"]["name"]:
                    x = copy.deepcopy(c)
                    x["steps"][lst]["pseudos"][j]["arg"]["name"] = other
                    alts.append(x)
            if p["kind"] == "scope" and isinstance(p["arg"], dict):
                x = copy.deepcopy(c)
                x["steps"][lst]["pseudos"][j] = P("has", S(p["arg"]["sel"], p["arg"]["name"]))
                pool = self.class_names if p["arg"]["sel"] == self.class_sel else self.fn_names
                other = self.pick(pool, limit=5) if pool else None
                if other and other != p["arg"]["name"]:
                    y = copy.deepcopy(c)
                    y["steps"][lst]["pseudos"][j]["arg"]["name"] = other
                    alts.append(y)
            if p["kind"] == "called-by" and self.fn_names:
                other = self.pick(self.fn_names, limit=3)
                if other and other != p["arg"]:
                    x = copy.deepcopy(c)
                    x["steps"][lst]["pseudos"][j]["arg"] = other
                    alts.append(x)
        for j, a in enumerate(st.get("attrs") or []):
            if a[0] == "receiver" and self.receivers:
                other = self.pick(self.receivers)
                if other != a[2]:
                    x = copy.deepcopy(c)
                    x["steps"][lst]["attrs"][j][2] = other
                    alts.append(x)
            if a[0] == "name":
                for op in ("^=", "$=", "*="):
                    if op != a[1]:
                        x = copy.deepcopy(c)
                        x["steps"][lst]["attrs"][j][1] = op
                        alts.append(x)
            if a[0] == "params":
                for v in (a[2] - 1, a[2] + 1):
                    if v >= 0:
                        x = copy.deepcopy(c)
                        x["steps"][lst]["attrs"][j][2] = v
                        alts.append(x)
        for i, s in enumerate(c["steps"]):
            if s.get("name") is not None and s["sel"] in self.names:
                other = self.pick(self.names[s["sel"]])
                if other and other != s["name"]:
                    x = copy.deepcopy(c)
                    x["steps"][i]["name"] = other
                    alts.append(x)
        if len(c["steps"]) == 2:
            for op in OPS:
                if op != c["op"]:
                    x = copy.deepcopy(c)
                    x["op"] = op
                    alts.append(x)
        alts += O.relaxed(c)
        if tier(c) == 1:
            alts += [C(S(o)) for o in rng.sample(self.steps, min(4, len(self.steps))) if o != st["sel"]]
        rng.shuffle(alts)
        out, empty, css = [], [], render(c)
        for x in alts:
            xs = render(x)
            if xs == css or xs in [render(o) for o in out + empty] or O.parse(xs) is None:
                continue
            got = self.t.select(x)
            if got == ref:
                continue
            (out if got else empty).append(x)
        return (out + empty)[:2]

    def run(self, n_total, families=None):
        quota = {f: q for f, q in QUOTA.items() if not families or f in families}
        total = sum(quota.values())
        want = {f: max(1, round(n_total * q / total)) for f, q in quota.items()}
        pools, seen = collections.defaultdict(list), set()
        for fam, n in want.items():
            tries = 0
            while len(pools[fam]) < 4 * n and tries < 400 * n:
                tries += 1
                c = self.propose(fam)
                if not c:
                    continue
                css = render(c)
                if css in seen or O.parse(css) != c:
                    seen.add(css)
                    continue
                seen.add(css)
                t = tier(c)
                if t >= 2 and css in self.eval_css:
                    continue
                lst = c["steps"][-1]
                if any(p["kind"] in ("has", "not-has") and p["arg"]["sel"] in (lst["sel"], ".fn")
                       for p in lst.get("pseudos") or []):
                    continue  # X:has(X), :has(.fn): the keyword-token leak (#133) on every language
                ref = self.t.select(c)
                if not 1 <= len(ref) <= 50 or (fam in ("attr", "refs", "mods") and len(ref) < 2):
                    continue
                if any(self.t.select(x) == ref for x in O.relaxed(c)):
                    continue
                dg = self.t.digest(ref)
                if dg in self.taken:
                    continue
                dis = self.distractors(c, ref)
                if len(dis) < 2:
                    continue
                pools[fam].append((c, css, ref, dg, dis))
        chosen = []
        for fam, n in want.items():
            keyed = sorted(pools[fam], key=lambda it: -self.rng.random() ** (
                1.0 / ((1.0 / (1 + self.train_shapes[shape(it[1])])) * (1.0 if 2 <= len(it[2]) <= 30 else 0.4))))
            got = 0
            for it in keyed:
                if got >= n:
                    break
                if it[3] in self.taken:
                    continue
                self.taken.add(it[3])
                chosen.append((fam,) + it)
                got += 1
        return chosen, {f: len(p) for f, p in pools.items()}


def source_line(fp, line):
    fp = fp if os.path.isabs(fp) else os.path.join(HERE, fp)
    try:
        with open(fp, errors="replace") as fh:
            for i, text in enumerate(fh, 1):
                if i == line:
                    return text.strip()[:110]
    except OSError:
        pass
    return ""


def taken_node_sets(extra_roots=()):
    shapes, taken, eval_css = collections.Counter(), set(), set()
    for root in (os.path.join(HERE, "train"),) + tuple(extra_roots):
        for f in glob.glob(os.path.join(root, "pairs", "*.jsonl")):
            b = os.path.basename(f)
            if b.startswith("rejected-") or b.startswith("train-"):
                continue
            for line in open(f):
                p = json.loads(line)
                shapes[shape(p["css"])] += 1
                if p.get("reference"):
                    taken.add(p["reference"]["sha256"])
    for f in glob.glob(os.path.join(HERE, "pairs", "*.jsonl")) + glob.glob(os.path.join(HERE, "eval_t5", "pairs", "*.jsonl")):
        if not os.path.basename(f).startswith("rejected-"):
            for line in open(f):
                p = json.loads(line)
                if p.get("css"):
                    eval_css.add(p["css"])
                if p.get("reference"):
                    taken.add(p["reference"]["sha256"])
    return shapes, taken, eval_css


def cmd_enumerate(out, fixtures, per_fixture, seed, extra_roots=(), families=None, id_prefix=None):
    shapes, taken, eval_css = taken_node_sets(extra_roots)
    rows = []
    for fi, fx in enumerate(fixtures):
        lang = lang_of(fx) if fx.split("-")[0] in LANG_BY_PREFIX else "python"
        t = O.Tree(fx)
        rng = random.Random("%s:%s" % (seed, fx))
        t0 = time.time()
        chosen, pools = Enumerator(t, lang, rng, shapes, taken, eval_css).run(per_fixture, families)
        for j, (fam, c, css, ref, dg, dis) in enumerate(chosen):
            ex = sorted(ref)
            ex = [ex[i] for i in sorted(rng.sample(range(len(ex)), min(2, len(ex))))]
            rows.append({"id": ("%s-%02d%04d" % (id_prefix, fi, j)) if id_prefix else "tr-%s-t%d-g%02d%04d" % (lang, tier(c), fi, j),
                         "tier": tier(c), "fixture": fx,
                         "lang": lang, "family": fam, "css": css, "struct": c, "distractor_structs": dis,
                         "distractors": [render(d) for d in dis], "gloss": gloss(c, lang),
                         "pred": {"count": len(ref), "sha256": dg},
                         "examples": ["%s:%s  %s" % (os.path.basename(f), t.node[(f, nid)]["start_line"],
                                                     source_line(f, t.node[(f, nid)]["start_line"])) for f, nid in ex]})
        log(out, "enumerate %s: %d chosen %s from pools %s in %.0fs" % (
            fx, len(chosen), dict(collections.Counter(ch[0] for ch in chosen)), pools, time.time() - t0))
    os.makedirs(os.path.join(out, "candidates"), exist_ok=True)
    with open(os.path.join(out, "candidates", "selectors.jsonl"), "w") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    log(out, "enumerate: %d candidates, tiers %s, %d distinct shapes, %d new to training" % (
        len(rows), dict(collections.Counter(r["tier"] for r in rows)), len({shape(r["css"]) for r in rows}),
        sum(1 for r in rows if not shapes[shape(r["css"])])))


# ---------------------------------------------------------------- device helpers

def card_v2(lang):
    return open(os.path.join(HERE, "train", "cards", "v2", "card_%s.md" % lang)).read()


def device_session(models):
    import qualify as Q
    key = Q.auth_key()
    cat = Q.catalog(key)
    missing = [m for m in models if m not in cat]
    if missing:
        sys.exit("not on the device: %s" % missing)
    return Q, key, Q.model_types(key), cat, Q.running(key)[0]


def restore(Q, key, types, original, logf):
    if not original:
        return
    try:
        logf("restoring %s" % original)
        Q.ensure_loaded(key, original[0], logf, types)
        for extra in original[1:]:
            if extra not in Q.running(key)[0]:
                Q.mgmt("models/%s/start" % extra, key, "POST", timeout=180)
    except Exception as e:
        logf("RESTORE FAILED %s: %s" % (type(e).__name__, e))


def ask(Q, key, types, model, body, logf):
    Q.yield_npu(key, model, logf, max_wait=3600)
    try:
        return Q.chat(key, body)
    except Q.urllib.error.HTTPError as e:
        if e.code != 503:
            raise
        logf("  503 -- reloading %s, retrying once" % model)
        Q.ensure_loaded(key, model, logf, types)
        Q.yield_npu(key, model, logf, max_wait=3600)
        return Q.chat(key, body)


def json_lines(text):
    out = []
    for line in (text or "").splitlines():
        line = line.strip().rstrip(",")
        if line.startswith("{"):
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


# ---------------------------------------------------------------- word

WORD_SYSTEM = """You write the English side of training pairs for an astcss (CSS-style AST selector)
model. Each selector below is already correct and verified against real code; you write
what a developer would say or type to find exactly those nodes.

The selector vocabulary, for reference:

%(card)s

For each selector give three wordings that all mean exactly the selector:
- "nl": a typed search request, the way someone writes into a search box.
- a spoken request, the way someone says it aloud to their editor ("show me the
  functions in the Tokenizer class that call advance cursor but never raise").
- a question ("which functions ... ?").

Rules for all three:
- Plain English only. Never any of the characters # [ ] { } ( ) > ~ + : and never a dot
  directly before a word (no foo(), no self.x, no json.dumps).
- Never selector names (fn, var, member, mod, receiver, called-by). Say "functions",
  "variables", "files", "calls on conn", "called from", "never called", "unused".
- Keep every code name exactly as given (process_file, GitHubClient, test_).
- Be exact about every condition in the meaning: "directly inside" vs "anywhere inside",
  "contains" vs "does not contain", "its own body" vs nested functions, all conditions
  that are combined.
- The three must not be identical.

Answer with one JSON object per line and nothing else:
{"k": <number>, "nl": "...", "paraphrases": ["<spoken>", "<question>"]}"""


def cmd_word(out, chunk=6):
    logf = lambda m: log(out, m)  # noqa: E731
    cands = [json.loads(l) for l in open(os.path.join(out, "candidates", "selectors.jsonl"))]
    words_path = os.path.join(out, "words.json")
    words = json.load(open(words_path)) if os.path.exists(words_path) else {}
    if any(c["id"] not in words for c in cands):
        Q, key, types, cat, original = device_session([WORD_MODEL])
        try:
            Q.yield_npu(key, WORD_MODEL, logf, max_wait=3600)
            logf("word: %s loaded in %.0fs" % (WORD_MODEL, Q.ensure_loaded(key, WORD_MODEL, logf, types)))
            for rnd in (1, 2):
                by_fx = collections.defaultdict(list)
                for c in cands:
                    if c["id"] not in words:
                        by_fx[c["fixture"]].append(c)
                for fx, items in sorted(by_fx.items()):
                    system = WORD_SYSTEM % {"card": card_v2(items[0]["lang"]).strip()}
                    for i in range(0, len(items), chunk):
                        group = items[i:i + chunk]
                        user = "Fixture `%s` (%s).\n\n%s" % (fx, items[0]["lang"], "\n\n".join(
                            "k=%d\n  selector: %s\n  meaning: %s\n  %d matches, e.g.\n    %s" % (
                                k, c["css"], c["gloss"], c["pred"]["count"], "\n    ".join(c["examples"]))
                            for k, c in enumerate(group)))
                        if rnd == 2:
                            user += "\n\nAn earlier answer for these broke the rules; follow them exactly."
                        body = {"model": WORD_MODEL, "stream": True, "temperature": 0.6, "max_tokens": 2500,
                                "chat_template_kwargs": {"enable_thinking": False},
                                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
                        try:
                            res = ask(Q, key, types, WORD_MODEL, body, logf)
                        except Exception as e:
                            logf("  word %s: %s: %s" % (fx, type(e).__name__, e))
                            continue
                        ok = 0
                        for obj in json_lines(res["content"]):
                            try:
                                c = group[int(obj["k"])]
                            except (KeyError, ValueError, TypeError, IndexError):
                                continue
                            trial = dict(c, nl=str(obj.get("nl", "")).strip(),
                                         paraphrases=[s.strip() for s in obj.get("paraphrases") or [] if isinstance(s, str)][:2])
                            if not pilot.static_reasons(trial, "distinct"):
                                words[c["id"]] = {"nl": trial["nl"], "paraphrases": trial["paraphrases"], "round": rnd}
                                ok += 1
                        logf("  word r%d %-16s %5.1fs %d of %d" % (rnd, fx, res["latency_s"], ok, len(group)))
                        with open(words_path + ".tmp", "w") as fh:
                            json.dump(words, fh, indent=1)
                        os.replace(words_path + ".tmp", words_path)
        finally:
            restore(Q, key, types, original, logf)
    worded = [dict(c, **words[c["id"]]) for c in cands if c["id"] in words]
    with open(os.path.join(out, "candidates", "worded.jsonl"), "w") as fh:
        for c in worded:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")
    logf("word: %d of %d worded" % (len(worded), len(cands)))


# ---------------------------------------------------------------- verify

def cmd_verify(out, batch):
    logf = lambda m: log(out, m)  # noqa: E731
    rows = [json.loads(l) for l in open(os.path.join(out, "candidates", "worded.jsonl"))]
    os.makedirs(os.path.join(out, "pairs"), exist_ok=True)
    for src in glob.glob(os.path.join(HERE, "train", "pairs", "accepted-*.jsonl")) + \
            glob.glob(os.path.join(HERE, "train", "pairs", "pending-*.jsonl")) + \
            glob.glob(os.path.join(HERE, "workspace", "sfgen", "pairs", "accepted-sf-*.jsonl")):
        dst = os.path.join(out, "pairs", "train-" + os.path.basename(src))
        if not os.path.lexists(dst):
            os.symlink(src, dst)
    t0 = time.time()
    res, meta = O.verify_batch(rows, batch, out, "distinct")
    meta["verify_s"] = round(time.time() - t0)
    json.dump(meta, open(os.path.join(out, "verify.json"), "w"), indent=1)
    logf("verify: %d accepted, %d pending, %d rejected in %.0fs; %s" % (
        len(res["accepted"]), len(res["pending"]), len(res["rejected"]), time.time() - t0, meta["tier_verdicts"]))


# ---------------------------------------------------------------- back-translate

def cmd_back(out, batch):
    logf = lambda m: log(out, m)  # noqa: E731
    kept = []
    for name in ("accepted", "pending"):
        f = os.path.join(out, "pairs", "%s-%s.jsonl" % (name, batch))
        kept += [json.loads(l) for l in open(f)] if os.path.exists(f) else []
    resp_path = os.path.join(out, "back.jsonl")
    done = set()
    if os.path.exists(resp_path):
        done = {(r["id"], r["text_index"]) for r in map(json.loads, open(resp_path)) if not r.get("error")}
    todo = [(p, k) for p in kept for k in range(1 + len(p["paraphrases"])) if (p["id"], k) not in done]
    lang = lambda p: lang_of(p["fixture"])  # noqa: E731
    if todo:
        Q, key, types, cat, original = device_session([BACK_MODEL])
        try:
            Q.yield_npu(key, BACK_MODEL, logf, max_wait=3600)
            logf("back: %s loaded in %.0fs, %d requests" % (BACK_MODEL, Q.ensure_loaded(key, BACK_MODEL, logf, types), len(todo)))
            with open(resp_path, "a") as fh:
                for p, k in todo:
                    text = ([p["nl"]] + p["paraphrases"])[k]
                    body, _ = Q.request_body(BACK_MODEL, cat[BACK_MODEL], card_v2(lang(p)), text)
                    row = {"id": p["id"], "text_index": k, "text": text}
                    try:
                        row.update(ask(Q, key, types, BACK_MODEL, body, logf))
                        row["prediction"] = Q.extract(row["content"])
                    except Exception as e:
                        row["error"] = "%s: %s" % (type(e).__name__, e)
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                    fh.flush()
        finally:
            restore(Q, key, types, original, logf)
    by_id = {p["id"]: p for p in kept}
    trees = {}
    with open(os.path.join(out, "back.scored.jsonl"), "w") as fh:
        for r in map(json.loads, open(resp_path)):
            if r.get("error") or r["id"] not in by_id:
                continue
            p = by_id[r["id"]]
            t = trees.setdefault(p["fixture"], O.Tree(p["fixture"]))
            s = O.parse(r.get("prediction") or "")
            r["parsed"] = s is not None
            r["match"] = bool(s) and t.digest(t.select(s)) == p["reference"]["sha256"]
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    logf("back: scored")


def cmd_report(out, batch):
    sel = [json.loads(l) for l in open(os.path.join(out, "candidates", "selectors.jsonl"))]
    load = lambda n: [json.loads(l) for l in open(os.path.join(out, "pairs", "%s-%s.jsonl" % (n, batch)))] \
        if os.path.exists(os.path.join(out, "pairs", "%s-%s.jsonl" % (n, batch))) else []  # noqa: E731
    acc, pend, rej = load("accepted"), load("pending"), load("rejected")
    back = collections.defaultdict(dict)
    if os.path.exists(os.path.join(out, "back.scored.jsonl")):
        for r in map(json.loads, open(os.path.join(out, "back.scored.jsonl"))):
            back[r["id"]][r["text_index"]] = r["match"]
    fam = {c["id"]: c["family"] for c in sel}
    kept = [p for p in acc + pend if any(back[p["id"]].values())]
    lines = ["# gen_pairs %s" % batch, "",
             "| tier | candidates | accepted | pending (documented, engine defect) | rejected | any wording back-translates |",
             "|---|---|---|---|---|---|"]
    for t in (1, 2, 3, 4, 5):
        f = lambda rs: [r for r in rs if r["tier"] == t]  # noqa: E731
        lines.append("| T%d | %d | %d | %d | %d | %d |" % (t, len(f(sel)), len(f(acc)), len(f(pend)), len(f(rej)), len(f(kept))))
    lines += ["", "Pending by issue: %s" % dict(collections.Counter(tag for p in pend for tag in p["tags"]))]
    lines += ["By family (candidates / accepted+pending / kept): " + ", ".join(
        "%s %d/%d/%d" % (f, sum(1 for c in sel if c["family"] == f), sum(1 for p in acc + pend if fam.get(p["id"]) == f),
                         sum(1 for p in kept if fam.get(p["id"]) == f)) for f in QUOTA)]
    per_text = collections.Counter((k, v) for m in back.values() for k, v in m.items())
    lines += ["Back-translation per wording (typed, spoken, question): " + ", ".join(
        "%d/%d" % (per_text[(k, True)], per_text[(k, True)] + per_text[(k, False)]) for k in (0, 1, 2))]
    reasons = collections.Counter(re.sub(r"'[^']*'|\d+|\([^)]*\)|\"[^\"]*\"|\S*[.#:\[]\S*", "_", w)[:80]
                                  for r in rej for w in r.get("reasons", []))
    lines += ["", "Rejection reasons:"] + ["- %s: %d" % kv for kv in reasons.most_common(12)]
    open(os.path.join(out, "REPORT.md"), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=("enumerate", "word", "verify", "back", "report"))
    ap.add_argument("--batch", default="gp-1")
    ap.add_argument("--out", required=True)
    ap.add_argument("--fixtures", required=True)
    ap.add_argument("--per-fixture", type=int, default=200)
    ap.add_argument("--seed", default="gen-pairs-1")
    ap.add_argument("--families", help="comma-separated subset of %s" % ",".join(QUOTA))
    ap.add_argument("--id-prefix", help="candidate ids <prefix>-<fixture#><n> instead of tr-<lang>-t<tier>-g...")
    args = ap.parse_args()
    out = os.path.join(HERE, args.out)
    if args.stage == "enumerate":
        cmd_enumerate(out, args.fixtures.split(","), args.per_fixture, args.seed,
                      extra_roots=(os.path.join(HERE, "workspace", "sfgen"),),
                      families=set(args.families.split(",")) if args.families else None, id_prefix=args.id_prefix)
    elif args.stage == "word":
        cmd_word(out)
    elif args.stage == "verify":
        cmd_verify(out, args.batch)
    elif args.stage == "back":
        cmd_back(out, args.batch)
    elif args.stage == "report":
        cmd_report(out, args.batch)


if __name__ == "__main__":
    main()
