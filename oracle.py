"""Reference semantics for astcss selectors, as sitting_duck documents them.

verify.py's rule is that the engine is the verifier. Tier 5 (relational and compound
selectors) needs features the engine implements wrongly today -- :scope(selector) #145,
:calls #146, :is-referenced #147, :exported #148, chained receivers #149, attribute filters
inside :has #150 -- and the decision (Teague, 2026-09-15) is to write pairs against the
documented meaning now and patch the engine later. This module is that documented meaning,
computed in Python over the node table the engine itself produces:

  extract(fixtures)       one engine session per fixture: node columns plus every card
                          class's node set (class membership stays the engine's own answer)
  Tree(fixture).select(c) the documented node set of a selector struct
  classify(...)           the engine's answer for the same selector: agreement -> verified;
                          a disagreement a filed issue explains -> pending_engine:<issue>;
                          anything else -> rejected (a bug here, or an unfiled one)
  verify_batch(...)       gates for a batch of candidate pairs, written like pilot.py

Where the engine is right, this reproduces it: its predecessor (workspace/sfgen.py) matched
the engine on 345 of 352 selector-first candidates across T1-T4 and all four combinators;
the 7 differences are :has keyword-token leaks (#133). `python3 oracle.py selftest`
re-checks that and the documented cases from the filed issues.

Selector struct (render() gives the selector text):

  {"steps": [step] or [step, step], "op": None | " " | ">" | "~" | "+"}
  step = {"sel": ".fn" | "function_definition", "name": str | None,
          "attrs": [[attr, op, value], ...],      # attr: name receiver signature annotation params
          "pseudos": [{"kind": k, "arg": a}, ...]}
  kind: has not-has (arg: step)  calls called-by (arg: name or None)  scope (arg: type or step)
        is-called is-referenced exported decorated async typed (no arg)

As on the card, attrs and pseudos go on the last step only; the first step takes a #name.
"""
import collections
import copy
import csv
import glob
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import verify as V  # noqa: E402

CACHE = os.path.join(HERE, "workspace", "oracle")
CLASSES = [".fn", ".class", ".var", ".call", ".member", ".import", ".if", ".loop", ".jump", ".try", ".catch",
           ".throw", ".comp", ".mod"]
FN, CLS = "DEFINITION_FUNCTION", "DEFINITION_CLASS"
DEFINITIONS = ("DEFINITION_FUNCTION", "DEFINITION_CLASS", "DEFINITION_VARIABLE")
EXPORTED_BIT = 16          # IS_EXPORTED (#65): public functions carry flags 30, _private_helper 14
DEF_NAME_CONTEXTS = {"in_function_definition", "in_class_definition", "in_parameters", "in_typed_parameter",
                     "in_default_parameter", "in_typed_default_parameter", "in_lambda_parameters"}
CHAINED_OBJECT_TYPES = {"attribute", "member_expression", "field_expression", "field_access", "call",
                        "call_expression", "method_invocation", "scoped_identifier", "subscript"}
ISSUES = {"scope-selector": 145, "calls-scope": 146, "is-referenced": 147, "exported": 148,
          "chained-receiver": 149, "attr-in-has": 150, "has-keyword-tokens": 133, "called-by-lambda": 152,
          # refined call codes (Rust macro_invocation 211, JS new_expression 210) are not
          # = 'COMPUTATION_CALL' in the macros' call-graph conditions (#152, second comment)
          "call-code-literal": 152,
          # C++ templates (2026-09-15): template_function/template_method use sites are classified as
          # definitions and the call around them has no name (#158); :templated is a proposal (#159)
          "template-call-name": 158, "templated": 159,
          # A bare type is a PREFIX match (#151), so `import_spec` also returns import_spec_list and
          # `column_definition` also returns the column_definitions container. Only detectable against
          # a fixture -- classify() adds it when the tree holds a longer type with the same prefix.
          "type-prefix": 151}
# Documented post-#158 semantics: a call whose callee is a template_function/template_method (directly,
# or through qualified_identifier / field_expression) takes that template's name. Off by default so the
# engine-agreement pipelines keep today's names; the template batch turns it on.
DOCUMENTED_TEMPLATE_CALL_NAMES = False
TEMPLATE_NAME_TYPES = {"template_function", "template_method"}
_extra_fixtures = {}


def register(name, pattern):
    """A fixture outside verify.FIXTURES (tests): name -> absolute glob."""
    _extra_fixtures[name] = pattern
    V.FIXTURES.setdefault(name, pattern)


def pattern_of(fx):
    return _extra_fixtures.get(fx) or os.path.join(HERE, V.FIXTURES[fx])


def cache(fx, *p):
    return os.path.join(CACHE, fx, *p)


# ---------------------------------------------------------------- extract

def extract(fixtures, jobs=None, force=False):
    import concurrent.futures

    def one(fx):
        if os.path.exists(cache(fx, "atoms.json")) and not force:
            return "%s: cached" % fx
        os.makedirs(cache(fx), exist_ok=True)
        lines = ["CREATE TABLE t AS SELECT * FROM read_ast('%s');" % V._q(pattern_of(fx)),
                 "COPY (SELECT file_path, node_id, parent_id, sibling_index, descendant_count, depth, type, "
                 "semantic_type::VARCHAR AS sem, flags, start_line, end_line, "
                 "CASE WHEN length(name) <= 120 AND strpos(name, chr(10)) = 0 THEN name END AS name, receiver, "
                 "CASE WHEN length(annotations) <= 300 THEN replace(annotations, chr(10), ' ') END AS annotations, "
                 "array_to_string(modifiers, '|') AS modifiers, "
                 "CASE WHEN length(signature_type) <= 120 THEN replace(signature_type, chr(10), ' ') END AS signature_type, "
                 "len(parameters) AS nparams FROM t) TO '%s' (FORMAT csv, HEADER);" % V._q(cache(fx, "nodes.csv"))]
        for i, s in enumerate(CLASSES):
            lines += ["SELECT '@@BEGIN a%d';" % i,
                      "COPY (SELECT file_path, node_id FROM ast_select_from('t', '%s')) TO '%s' (FORMAT csv, HEADER);"
                      % (V._q(s), V._q(cache(fx, "atom%d.csv" % i))),
                      "SELECT '@@ROWS ok';"]
        t0 = time.time()
        got = V._collect(V._run_script(lines), "@@ROWS")
        atoms, errors = {}, []
        for i, s in enumerate(CLASSES):
            f = cache(fx, "atom%d.csv" % i)
            r = got.get("a%d" % i, {"error": "no output"})
            if "error" in r or not os.path.exists(f):
                errors.append("%s: %s" % (s, r.get("error")))
                continue
            with open(f, newline="") as fh:
                atoms[s] = [[x["file_path"], int(x["node_id"])] for x in csv.DictReader(fh)]
            os.remove(f)
        if errors or not os.path.exists(cache(fx, "nodes.csv")):
            return "%s: FAILED (%s)" % (fx, errors[:2])
        json.dump(atoms, open(cache(fx, "atoms.json"), "w"))
        return "%s: %d classes in %.0fs" % (fx, len(atoms), time.time() - t0)

    jobs = jobs or max(1, int(os.environ.get("ASTCSS_EXEC_JOBS", "4")))
    with concurrent.futures.ThreadPoolExecutor(max(1, min(jobs, len(fixtures)))) as ex:
        return list(ex.map(one, fixtures))


# ---------------------------------------------------------------- rendering

def rattr(a):
    attr, op, val = a
    if attr == "params":
        return "[params=%s]" % val
    return '[%s%s"%s"]' % (attr, op, val)


def rpseudo(p):
    kind, arg = p["kind"], p.get("arg")
    if kind == "has":
        return ":has(%s)" % rstep(arg)
    if kind == "not-has":
        return ":not(:has(%s))" % rstep(arg)
    if kind == "not":
        return ":not(%s)" % rpseudo(arg)
    if arg is None:
        return ":" + kind
    return ":%s(%s)" % (kind, rstep(arg) if isinstance(arg, dict) else arg)


def rstep(st):
    s = st["sel"]
    if st.get("name") is not None:
        s += "#" + st["name"]
    return s + "".join(rattr(a) for a in st.get("attrs") or []) + "".join(rpseudo(p) for p in st.get("pseudos") or [])


ELEMENTS = ("callers", "callees", "scope")
# node_config.hpp: bit 3, "creates scope boundary". The engine's :scope is is_scope(flags) and
# ::scope joins each match to scope.current, its nearest enclosing boundary.
IS_SCOPE_BIT = 0x08


def render(c):
    steps = c["steps"]
    if len(steps) == 1:
        s = rstep(steps[0])
    else:
        s = rstep(steps[0]) + (" " if c["op"] == " " else " %s " % c["op"]) + rstep(steps[1])
    return s + ("::" + c["element"] if c.get("element") else "")


def last(c):
    return c["steps"][-1]


def tier(c):
    """T5 = relational or compound: two or more constraints on a node (a step plus a
    pseudo-class, two pseudo-classes), or a call-graph, scope, receiver, signature,
    annotation or modifier test. T1-T4 keep their original meaning."""
    lst = last(c)
    ps, attrs = lst.get("pseudos") or [], lst.get("attrs") or []
    if c.get("element") or len(ps) >= 2 or (len(c["steps"]) == 2 and (ps or attrs)):
        return 5
    if any(p["kind"] not in ("has", "not-has") for p in ps) or any(a[0] not in ("name", "params") for a in attrs):
        return 5
    if any(isinstance(p.get("arg"), dict) and (p["arg"].get("attrs") or p["arg"].get("pseudos")) for p in ps):
        return 5
    if ps:
        return 4
    if len(c["steps"]) == 2:
        return 3
    return 2 if (lst.get("name") is not None or attrs) else 1


def features(c):
    """Documented features whose engine implementation has a filed defect."""
    fs = set()
    if c.get("element"):
        fs.add("call-code-literal")
    for st in c["steps"]:
        for a in st.get("attrs") or []:
            if a[0] == "receiver":
                fs.add("chained-receiver")
        for p in st.get("pseudos") or []:
            while p["kind"] == "not":
                p = p["arg"]
            k, arg = p["kind"], p.get("arg")
            if k == "scope" and isinstance(arg, dict):
                fs.add("scope-selector")
            elif k == "calls":
                fs.update(("calls-scope", "call-code-literal"))
            elif k == "is-called":
                fs.add("call-code-literal")
            elif k == "called-by":
                fs.add("called-by-lambda")   # the engine's nearest-function test skips lambdas (#152)
            elif k in ("is-referenced", "exported"):
                fs.add(k)
            elif k == "templated":
                fs.add("templated")
                if st.get("name") is not None and st["sel"] in (".call", "call_expression"):
                    fs.add("template-call-name")
            elif k in ("has", "not-has"):
                fs.add("has-keyword-tokens")
                if arg.get("attrs") or arg.get("pseudos"):
                    fs.add("attr-in-has")
    return fs


def relaxed(c):
    """verify.relaxations, on the struct: drop each #name, each [attr], each pseudo-class
    outside another's arguments, and the first combinator step."""
    out = []
    for i, st in enumerate(c["steps"]):
        if st.get("name") is not None:
            r = copy.deepcopy(c)
            r["steps"][i]["name"] = None
            out.append(r)
        for j in range(len(st.get("attrs") or [])):
            r = copy.deepcopy(c)
            del r["steps"][i]["attrs"][j]
            out.append(r)
        for j in range(len(st.get("pseudos") or [])):
            r = copy.deepcopy(c)
            del r["steps"][i]["pseudos"][j]
            out.append(r)
    if len(c["steps"]) == 2:
        r = copy.deepcopy(c)
        r["steps"], r["op"] = [r["steps"][1]], None
        out.append(r)
    if c.get("element"):
        r = copy.deepcopy(c)
        r["element"] = None
        out.append(r)
    return out


# ---------------------------------------------------------------- parsing selector text

_SEL = re.compile(r"\*|\.?[A-Za-z_][\w-]*")
_ID = re.compile(r"#([A-Za-z_][\w]*)")
_ATTR = re.compile(r"\[\s*([\w-]+)\s*(\^=|\$=|\*=|=)\s*(?:\"([^\"]*)\"|'([^']*)'|([^\]\s]*))\s*\]")
_PSEUDO = re.compile(r":([\w-]+)")
PSEUDO_KINDS = {"has", "not", "calls", "called-by", "is-called", "is-referenced", "exported", "scope", "in-scope", "decorated",
                "async", "typed", "templated"}


def _balanced(s, i):
    """s[i] == '(' -> index just past its matching ')' (quotes respected), or -1."""
    depth, quote = 0, None
    for j in range(i, len(s)):
        ch = s[j]
        if quote:
            quote = None if ch == quote else quote
        elif ch in "\"'":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return j + 1
    return -1


def _parse_pseudo(text):
    m = _PSEUDO.match(text)
    if not m or m.group(1) not in PSEUDO_KINDS:
        return None, 0
    kind, i = m.group(1), m.end()
    arg = None
    if i < len(text) and text[i] == "(":
        j = _balanced(text, i)
        if j < 0:
            return None, 0
        arg, i = text[i + 1:j - 1].strip(), j
    if kind == "has":
        st = parse_step(arg or "")
        return ({"kind": "has", "arg": st} if st else None), i
    if kind == "not":
        if arg and arg.startswith(":has("):
            inner, k = _parse_pseudo(arg)
            if inner and k == len(arg):
                return {"kind": "not-has", "arg": inner["arg"]}, i
            return None, 0
        inner, k = _parse_pseudo(arg or "")
        return ({"kind": "not", "arg": inner} if inner and k == len(arg) else None), i
    # :scope and :in-scope share one argument grammar (sitting_duck 2a1413d, #145): a keyword
    # (function|class|module), a semantic-class alias with an optional #name, or a bare node type.
    # `:scope(X)` asks whether the node IS a boundary of X; `:in-scope(X)` whether it sits INSIDE one.
    if kind in ("scope", "in-scope") and arg:
        if arg.startswith(".") or "#" in arg or "[" in arg or ":" in arg:
            st = parse_step(arg)
            return ({"kind": kind, "arg": st} if st else None), i
        return {"kind": kind, "arg": arg}, i
    if kind in ("calls", "called-by"):
        return {"kind": kind, "arg": arg.strip("\"'") if arg else None}, i
    if arg:
        return None, 0
    return {"kind": kind, "arg": None}, i


def parse_step(text):
    text = text.strip()
    m = _SEL.match(text)
    if not m:
        return None
    st, i = {"sel": m.group(0), "name": None, "attrs": [], "pseudos": []}, m.end()
    while i < len(text):
        rest = text[i:]
        if rest[0] == "#":
            mm = _ID.match(rest)
            if not mm or st["name"] is not None:
                return None
            st["name"], i = mm.group(1), i + mm.end()
        elif rest[0] == "[":
            mm = _ATTR.match(rest)
            if not mm:
                return None
            val = next(g for g in (mm.group(3), mm.group(4), mm.group(5)) if g is not None)
            if mm.group(1) == "params":
                if mm.group(2) != "=" or not val.isdigit():
                    return None
                val = int(val)
            st["attrs"].append([mm.group(1), mm.group(2), val])
            i += mm.end()
        elif rest[0] == ":":
            p, k = _parse_pseudo(rest)
            if not p:
                return None
            st["pseudos"].append(p)
            i += k
        else:
            return None
    return st


def parse(css):
    """Selector text -> struct, or None where the engine would refuse or the grammar here
    does not cover it (three steps, filters on the first step, unknown pseudo-classes)."""
    s = (css or "").strip()
    element = None
    m = re.search(r"::([\w-]+)$", s)
    if m:
        if m.group(1) not in ELEMENTS:
            return None
        element, s = m.group(1), s[:m.start()].strip()
    if "::" in s:
        return None
    parts, ops, depth, quote, cur, i = [], [], 0, None, "", 0
    while i < len(s):
        ch = s[i]
        if quote:
            quote = None if ch == quote else quote
            cur += ch
        elif ch in "\"'":
            quote = ch
            cur += ch
        elif ch in "([":
            depth += 1
            cur += ch
        elif ch in ")]":
            depth -= 1
            cur += ch
        elif depth == 0 and (ch.isspace() or ch in ">~+"):
            j = i
            op = " "
            while j < len(s) and (s[j].isspace() or s[j] in ">~+"):
                if s[j] in ">~+":
                    op = s[j]
                j += 1
            if cur:
                parts.append(cur)
                ops.append(op)
                cur = ""
            i = j
            continue
        else:
            cur += ch
        i += 1
    if cur:
        parts.append(cur)
    if not parts or len(parts) > 2 or len(ops) != len(parts) - 1:
        return None
    steps = [parse_step(p) for p in parts]
    if any(st is None for st in steps):
        return None
    if len(steps) == 2 and (steps[0]["attrs"] or steps[0]["pseudos"]):
        return None
    out = {"steps": steps, "op": ops[0] if ops else None}
    if element:
        out["element"] = element
    return out


# ---------------------------------------------------------------- the tree

class Tree:
    def __init__(self, fx):
        self.fx = fx
        self.node = {}
        self.by_type = collections.defaultdict(set)
        self.by_sem = collections.defaultdict(set)
        self.kids = collections.defaultdict(list)
        with open(cache(fx, "nodes.csv"), newline="") as fh:
            for r in csv.DictReader(fh):
                for col in ("node_id", "sibling_index", "descendant_count", "depth", "flags", "start_line", "end_line",
                            "nparams"):
                    r[col] = int(r[col]) if r[col] not in ("", None) else 0
                r["parent_id"] = int(r["parent_id"]) if r["parent_id"] not in ("", None) else None
                for col in ("name", "receiver", "annotations", "signature_type"):
                    r[col] = r[col] or None
                r["modifiers"] = set(filter(None, (r["modifiers"] or "").split("|")))
                k = (r["file_path"], r["node_id"])
                self.node[k] = r
                self.by_type[r["type"]].add(k)
                self.by_sem[r["sem"]].add(k)
                if r["parent_id"] is not None:
                    self.kids[(r["file_path"], r["parent_id"])].append(k)
        for v in self.kids.values():
            v.sort(key=lambda k: self.node[k]["sibling_index"])
        if DOCUMENTED_TEMPLATE_CALL_NAMES:
            for k, r in self.node.items():
                if r["type"] == "call_expression" and not r["name"]:
                    t = self.template_callee(k)
                    if t is not None and self.node[t]["name"]:
                        r["name"] = self.node[t]["name"]
        self.atoms = {s: {tuple(k) for k in keys} for s, keys in json.load(open(cache(fx, "atoms.json"))).items()}
        self._step, self._anc, self._near = {}, {}, {}

    # -- structure
    def parent(self, k):
        p = self.node[k]["parent_id"]
        return None if p is None else (k[0], p)

    def ancestors_of(self, k):
        p = self.parent(k)
        while p is not None:
            yield p
            p = self.parent(p)

    def template_callee(self, k):
        """The template_function/template_method a call goes through, if its callee carries an explicit
        template argument list: the callee itself, or its child under qualified_identifier/field_expression."""
        kids = self.kids.get(k) or []
        if not kids:
            return None
        callee = kids[0]
        if self.node[callee]["type"] in TEMPLATE_NAME_TYPES:
            return callee
        return next((c for c in self.kids.get(callee) or [] if self.node[c]["type"] in TEMPLATE_NAME_TYPES), None)

    def nearest(self, k, sem):
        key = (k, sem)
        if key not in self._near:
            self._near[key] = next((p for p in self.ancestors_of(k) if self.node[p]["sem"] == sem), None)
        return self._near[key]

    def base(self, sel):
        return self.atoms.get(sel, set()) if sel.startswith(".") else self.by_type.get(sel, set())

    def digest(self, keys):
        return V._digest(["%s:%s" % (os.path.basename(f), n) for f, n in sorted(keys)])

    def nodes_list(self, keys):
        return ["%s:%s" % (os.path.basename(f), n) for f, n in sorted(keys)]

    # -- documented attributes
    def receiver(self, k):
        """The object a method is invoked on; None for bare calls and chained receivers
        (css_selectors.sql doc comment). The engine keeps the last segment instead (#149)."""
        r = self.node[k]["receiver"]
        if r is None:
            return None
        kids = self.kids.get(k) or []
        fn = kids[0] if kids else None
        obj = (self.kids.get(fn) or [None])[0] if fn else None
        if obj is not None and self.node[obj]["type"] in CHAINED_OBJECT_TYPES:
            return None
        return r

    def attr_value(self, k, attr):
        n = self.node[k]
        return {"name": n["name"], "receiver": self.receiver(k) if attr == "receiver" else None,
                "signature": n["signature_type"], "annotation": n["annotations"]}.get(attr)

    def attr_ok(self, k, a):
        attr, op, val = a
        if attr == "params":
            return self.node[k]["nparams"] == int(val)
        v = self.attr_value(k, attr)
        if v is None:
            return False
        return {"=": v == val, "^=": v.startswith(val), "$=": v.endswith(val), "*=": val in v}[op]

    # -- steps and pseudo-classes
    def step(self, st):
        key = rstep(st)
        if key in self._step:
            return self._step[key]
        s = set(self.base(st["sel"]))
        if st.get("name") is not None:
            s = {k for k in s if self.node[k]["name"] == st["name"]}
        for a in st.get("attrs") or []:
            s = {k for k in s if self.attr_ok(k, a)}
        for p in st.get("pseudos") or []:
            s = self.pseudo(s, p)
        self._step[key] = s
        return s

    def containing(self, st):
        """Nodes with a descendant matching st."""
        key = rstep(st)
        if key not in self._anc:
            out = set()
            for k in self.step(st):
                p = self.parent(k)
                while p is not None and p not in out:
                    out.add(p)
                    p = self.parent(p)
            self._anc[key] = out
        return self._anc[key]

    def pseudo(self, s, p):
        kind, arg = p["kind"], p.get("arg")
        n = self.node
        if kind == "not":
            # :not(:is-called), :not(:decorated), ...: the complement within s
            return s - self.pseudo(s, arg)
        if kind in ("has", "not-has"):
            anc = self.containing(arg)
            return {k for k in s if (k in anc) == (kind == "has")}
        if kind == "calls":
            # Documented: the target's own scope makes the call -- a call inside a nested
            # function is attributed to that function, not to the one around it.
            calls = [c for c in self.by_sem["COMPUTATION_CALL"] if arg is None or n[c]["name"] == arg]
            fn_owner = {self.nearest(c, FN) for c in calls}
            cls_owner = {self.nearest(c, CLS) for c in calls if self.nearest(c, FN) is None
                         or self.nearest(self.nearest(c, FN), CLS) is not None}
            contains = set()
            for c in calls:
                contains.update(self.ancestors_of(c))
            return {k for k in s if (k in fn_owner if n[k]["sem"] == FN else
                                     k in cls_owner if n[k]["sem"] == CLS else k in contains)}
        if kind == "called-by":
            return {k for k in s if (lambda f: f is not None and (arg is None or n[f]["name"] == arg))(self.nearest(k, FN))}
        if kind == "is-called":
            called = {(c[0], n[c]["name"]) for c in self.by_sem["COMPUTATION_CALL"] if n[c]["name"]}
            return {k for k in s if n[k]["name"] and (k[0], n[k]["name"]) in called}
        if kind == "is-referenced":
            refs = collections.Counter()
            for k in self.by_sem["NAME_IDENTIFIER"]:
                if n[k]["name"] and not (n[k]["modifiers"] & DEF_NAME_CONTEXTS):
                    refs[(k[0], n[k]["name"])] += 1
            return {k for k in s if n[k]["name"] and n[k]["sem"] in DEFINITIONS and refs[(k[0], n[k]["name"])]}
        if kind == "exported":
            return {k for k in s if n[k]["sem"] in DEFINITIONS and n[k]["flags"] & EXPORTED_BIT
                    and self.nearest(k, FN) is None and self.nearest(k, CLS) is None}
        if kind == "in-scope":
            # CONTAINMENT: the node sits inside a scope matching the argument. This is what this
            # module always computed for `:scope(X)`; sitting_duck 2a1413d gave that meaning its own
            # name and left `:scope` for the boundary test below.
            if isinstance(arg, dict):
                # The engine reads the nearest enclosing SCOPE PROVIDER (a.scope.function /
                # .class / .module, precomputed at parse time), not the nearest node of the
                # class. The two differ wherever a class includes non-scope nodes: C++ `.fn`
                # covers function_declarator (#139), so a parameter's nearest `.fn` ancestor is
                # the declarator while its scope.function is the enclosing definition. Requiring
                # IS_SCOPE here reproduces the engine -- including for SQL, where create_table
                # is not a scope provider and the answer is legitimately empty (#166).
                kinds, target = self.base(arg["sel"]), self.step(arg)
                out = set()
                for k in s:
                    near = next((a for a in self.ancestors_of(k)
                                 if a in kinds and n[a]["flags"] & IS_SCOPE_BIT), None)
                    if near is not None and near in target:
                        out.add(k)
                return out
            return {k for k in s if any(n[a]["type"] == arg or n[a]["type"].startswith(arg + "_")
                                        for a in self.ancestors_of(k))}
        if kind == "scope":
            # BOUNDARY: the node itself creates a scope (IS_SCOPE), optionally of a given kind or name.
            boundary = {k for k in s if n[k]["flags"] & IS_SCOPE_BIT}
            if arg is None:
                return boundary
            if isinstance(arg, dict):
                return boundary & self.step(arg)
            return {k for k in boundary if n[k]["type"] == arg or n[k]["type"].startswith(arg + "_")}
        if kind == "decorated":
            return {k for k in s if n[k]["annotations"]}
        if kind == "async":
            return {k for k in s if "async" in n[k]["modifiers"]}
        if kind == "typed":
            return {k for k in s if n[k]["signature_type"]}
        if kind == "templated":
            # Proposed (#159): a definition directly inside template_declaration, or a call whose callee
            # carries an explicit template argument list (make_uniq<T>(...), obj.Cast<T>()).
            out = set()
            for k in s:
                par = self.parent(k)
                if par is not None and n[par]["type"] == "template_declaration":
                    out.add(k)
                elif n[k]["type"] == "call_expression" and self.template_callee(k) is not None:
                    out.add(k)
            return out
        raise ValueError("unknown pseudo-class %r" % kind)

    # -- node -> selector (DevTools "Copy selector")
    def classes_of(self, k):
        return [s for s in CLASSES if k in self.atoms.get(s, ())]

    def anchor_steps(self, k):
        """One-step selectors that match k, most readable first: class or type, with the
        node's name, and the attributes it carries."""
        n = self.node[k]
        sels = self.classes_of(k) + [n["type"]]
        out = []
        for sel in sels:
            base = S(sel)
            out.append(base)
            if n["name"] and re.match(r"^[A-Za-z_][\w]*$", n["name"]):
                out.append(S(sel, n["name"]))
            rv = self.receiver(k)
            if rv and re.match(r"^[A-Za-z_][\w]*$", rv):
                out.append(S(sel, n["name"] if n["name"] and re.match(r"^[A-Za-z_][\w]*$", n["name"]) else None,
                             [["receiver", "=", rv]]))
            if n["sem"] == FN:
                out.append(S(sel, n["name"] if n["name"] and re.match(r"^[A-Za-z_][\w]*$", n["name"]) else None,
                             [["params", "=", n["nparams"]]]))
                if n["signature_type"] and re.match(r"^[A-Za-z_][\w.]*$", n["signature_type"]):
                    out.append(S(sel, n["name"] if n["name"] else None, [["signature", "=", n["signature_type"]]]))
        return out

    def selector_for(self, k, limit=5):
        """Selectors for one node, ranked like DevTools' "Copy selector": exactly this node
        first, then fewest extra matches, then shortest. Two steps at most (the engine's
        limit, #127) and no file filter, so identical code in two files can stay ambiguous;
        each result carries its match count. Semantics are the documented ones (Tree.select)."""
        n = self.node[k]
        cands = [C(st) for st in self.anchor_steps(k)]
        # Scope anchors: the nearest named function and class around the node, and its
        # named parent, joined with ' ' (anywhere inside) or '>' (direct child).
        anchors = []
        for sem in (FN, CLS):
            a = self.nearest(k, sem)
            if a is not None and self.node[a]["name"] and re.match(r"^[A-Za-z_][\w]*$", self.node[a]["name"]):
                anchors.append((a, " "))
        p = self.parent(k)
        if p is not None and self.node[p]["name"] and re.match(r"^[A-Za-z_][\w]*$", self.node[p]["name"]):
            anchors.append((p, ">"))
        targets = self.anchor_steps(k)
        for a, op in anchors:
            for ast in [s for s in self.anchor_steps(a) if s.get("name") and not s.get("attrs")][:2]:
                for tst in targets:
                    cands.append(C(ast, tst, op=op))
        seen, ranked = set(), []
        for c in cands:
            css = render(c)
            if css in seen or parse(css) != c:
                continue
            seen.add(css)
            got = self.select(c)
            if k not in got:
                continue
            ranked.append((len(got) != 1, len(got), len(css), css, c))
        ranked.sort(key=lambda r: r[:3])
        return [{"selector": css, "matches": cnt, "unique": not amb} for amb, cnt, _, css, _ in ranked[:limit]]

    def select(self, c):
        base = self._select_steps(c)
        el = c.get("element")
        if not el:
            return base
        n = self.node
        if el == "callers":
            # Documented: the functions that call the matched function -- for every call
            # to its name in the same file, the function that call sits in directly.
            names = {(k[0], n[k]["name"]) for k in base if n[k]["name"]}
            out = set()
            for call in self.by_sem["COMPUTATION_CALL"]:
                if (call[0], n[call]["name"]) in names and call not in base:
                    f = self.nearest(call, FN)
                    if f is not None:
                        out.add(f)
            return out
        if el == "scope":
            # ::scope -- each match's nearest enclosing scope boundary (the engine joins on
            # scope.current). A set here: two matches in one function yield that function once.
            out = set()
            for k in base:
                anc = next((a for a in self.ancestors_of(k) if n[a]["flags"] & IS_SCOPE_BIT), None)
                if anc is not None:
                    out.add(anc)
            return out
        # callees: the named calls inside the matched function, nested functions included
        out = set()
        for call in self.by_sem["COMPUTATION_CALL"]:
            if not n[call]["name"]:
                continue
            if any(p in base for p in self.ancestors_of(call)):
                out.add(call)
        return out

    def _select_steps(self, c):
        steps = c["steps"]
        if len(steps) == 1:
            return self.step(steps[0])
        A, B, op = self.step(steps[0]), self.step(steps[1]), c["op"]
        if op == " ":
            return {x for x in B if any(p in A for p in self.ancestors_of(x))}
        if op == ">":
            return {x for x in B if self.parent(x) in A}
        if op == "~":
            first = {}
            for a in A:
                p = self.parent(a)
                if p is not None:
                    first[p] = min(first.get(p, 1 << 30), self.node[a]["sibling_index"])
            return {x for x in B if self.parent(x) in first and self.node[x]["sibling_index"] > first[self.parent(x)]}
        pos = {(self.parent(a), self.node[a]["sibling_index"]) for a in A}
        return {x for x in B if (self.parent(x), self.node[x]["sibling_index"] - 1) in pos}


# ---------------------------------------------------------------- engine comparison and gates

def prefix_types(tree, c):
    """Bare types in the selector that are a PREFIX of another type in this fixture (#151): the
    engine returns those too, so a disagreement of exactly that size is the filed defect, not a
    defect here. `import_spec` picks up import_spec_list; `column_definition` picks up
    column_definitions."""
    out = {}
    for st in c["steps"]:
        sel = st.get("sel") or ""
        if sel.startswith(".") or sel == "*":
            continue
        longer = sorted(t for t in tree.by_type if t != sel and t.startswith(sel))
        if longer:
            out[sel] = longer
    return out


def classify(c, oracle_digest, engine, tree=None):
    """engine: {"nodes": [...]} or {"error": str}. -> ("verified" | "pending" | "rejected", detail)."""
    fs = features(c)
    if "error" in engine:
        if "attr-in-has" in fs:
            return "pending", ["pending_engine:attr-in-has#150"]
        if "templated" in fs:
            # the engine has no :templated yet (#159) and refuses it
            return "pending", ["pending_engine:%s#%d" % (f, ISSUES[f]) for f in sorted(fs & {"templated", "template-call-name"})]
        return "rejected", ["engine refuses the selector: %s" % engine["error"][:160]]
    if V._digest(engine["nodes"]) == oracle_digest:
        return "verified", []
    explained = sorted(f for f in fs if f in ISSUES)
    if explained:
        return "pending", ["pending_engine:%s#%d" % (f, ISSUES[f]) for f in explained]
    if tree is not None and len(engine["nodes"]) > 0:
        pre = prefix_types(tree, c)
        if pre:
            return "pending", ["pending_engine:type-prefix#%d" % ISSUES["type-prefix"]]
    return "rejected", ["engine (%d nodes) and documented semantics disagree, and no filed issue explains it"
                        % len(engine["nodes"])]


def gate_reasons(tree, c, ref, distractors):
    reasons = []
    if not 1 <= len(ref) <= 50:
        reasons.append("reference returns %d nodes (need 1..50)" % len(ref))
    for r in relaxed(c):
        if tree.select(r) == ref:
            reasons.append("%s is not load-bearing (same nodes as %s)" % (render(c), render(r)))
    if len(distractors) < 2:
        reasons.append("fewer than 2 distractors")
    for d in distractors:
        if tree.select(d) == ref:
            reasons.append("distractor %s matches the reference" % render(d))
    return reasons


def verify_batch(rows, batch, root, paraphrase_rule="distinct", check_eval_overlap=True, engine=True, taken=None):
    """rows: dicts with id, fixture, nl, paraphrases, struct, distractor_structs (and optional
    tags). Writes <root>/pairs/{accepted,pending,rejected}-<batch>.jsonl and <root>/batches/<batch>.json.
    Oracle gates decide; the engine decides only accepted (agrees) vs pending (a filed defect)."""
    import pilot
    trees = {}
    for fx in sorted({r["fixture"] for r in rows}):
        trees[fx] = Tree(fx)
    seen = dict(taken or {})
    for prior in sorted(glob.glob(os.path.join(root, "pairs", "*.jsonl"))):
        name = os.path.basename(prior)
        if name.startswith("rejected-") or name.endswith("-%s.jsonl" % batch):
            continue
        for line in open(prior):
            p = json.loads(line)
            if p.get("reference"):
                seen[(p["fixture"], p["reference"]["sha256"])] = p["id"]
    overlap = pilot.eval_overlap([dict(r, css=render(r["struct"]), tier=tier(r["struct"])) for r in rows]) \
        if check_eval_overlap else {}
    prepared = []
    for r in rows:
        t = trees[r["fixture"]]
        c = r["struct"]
        ref = t.select(c)
        prepared.append((r, t, c, ref, t.digest(ref)))
    got = {}
    if engine:
        # One fixture at a time: V.execute shards queries over ASTCSS_EXEC_JOBS processes and
        # each materializes every fixture in its shard, so a many-fixture batch held N copies
        # of every AST at once (2026-09-15: the 12-candidate smoke batch across 12 fixtures
        # ran the machine out of memory).
        by_fx = collections.defaultdict(list)
        for r, t, c, ref, dg in prepared:
            by_fx[r["fixture"]].append((r["id"], r["fixture"], render(c)))
        for fx in sorted(by_fx):
            got.update(V.execute(by_fx[fx]))
    out = {"accepted": [], "pending": [], "rejected": []}
    agreement = collections.Counter()
    for r, t, c, ref, dg in prepared:
        css = render(c)
        dis = r.get("distractor_structs") or []
        reasons = pilot.static_reasons(dict(r, distractors=[render(d) for d in dis]), paraphrase_rule)
        reasons += gate_reasons(t, c, ref, dis)
        if r["id"] in overlap:
            reasons.append(overlap[r["id"]])
        verdict, detail = ("verified", []) if not engine else classify(c, dg, got.get(r["id"], {"error": "no output"}), t)
        agreement["%s:%s" % (tier(c), verdict)] += 1
        if verdict == "rejected":
            reasons += detail
        key = (r["fixture"], dg)
        if not reasons:
            if key in seen:
                reasons.append("same node set as %s on %s" % (seen[key], r["fixture"]))
            else:
                seen[key] = r["id"]
        row = {"id": r["id"], "tier": tier(c), "nl": r.get("nl"), "paraphrases": r.get("paraphrases"), "css": css,
               "fixture": r["fixture"], "distractors": [render(d) for d in dis], "treeql": None,
               "struct": c,
               "verification": {"batch": batch, "method": "oracle+engine" if engine else "oracle",
                                "engine": verdict, "relaxations": [render(x) for x in relaxed(c)]},
               "reference": {"count": len(ref), "sha256": dg, "nodes": t.nodes_list(ref),
                             "source": "engine" if verdict == "verified" else "oracle"}}
        if reasons:
            row["tags"], row["reasons"] = ["rejected"], reasons
            out["rejected"].append(row)
        elif verdict == "pending":
            row["tags"] = detail
            out["pending"].append(row)
        else:
            row["tags"] = ["sitting_duck_supported", "v0"] + (r.get("tags") or [])
            out["accepted"].append(row)
    os.makedirs(os.path.join(root, "pairs"), exist_ok=True)
    os.makedirs(os.path.join(root, "batches"), exist_ok=True)
    for name, data in out.items():
        dest = os.path.join(root, "pairs", "%s-%s.jsonl" % (name, batch))
        with open(dest + ".tmp", "w") as fh:
            for row in data:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        os.replace(dest + ".tmp", dest)
    meta = {"batch": batch, "when": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "engine": V.engine_identity(),
            "verifier": "oracle.py documented semantics; engine agreement recorded", "paraphrase_rule": paraphrase_rule,
            "candidates": len(rows), **{k: len(v) for k, v in out.items()}, "tier_verdicts": dict(agreement)}
    dest = os.path.join(root, "batches", "%s.json" % batch)
    with open(dest + ".tmp", "w") as fh:
        json.dump(meta, fh, indent=2, sort_keys=True)
    os.replace(dest + ".tmp", dest)
    return out, meta


# ---------------------------------------------------------------- self-test

def S(sel, name=None, attrs=None, pseudos=None):
    return {"sel": sel, "name": name, "attrs": attrs or [], "pseudos": pseudos or []}


def P(kind, arg=None):
    return {"kind": kind, "arg": arg}


def C(*steps, op=None):
    return {"steps": list(steps), "op": op}


def from_sfgen(c):
    """workspace/sfgen.py's struct -> this module's."""
    def st(x):
        attrs = []
        if x.get("attr"):
            attrs.append(["name", x["attr"][0] + "=", x["attr"][1]])
        if x.get("params") is not None:
            attrs.append(["params", "=", x["params"]])
        return S(x["sel"], x.get("name"), attrs)
    steps = [st(c["a"])] + ([st(c["b"])] if c.get("op") else [])
    if c.get("has"):
        steps[-1]["pseudos"].append(P("not-has" if c["has"]["neg"] else "has", st(c["has"]["s"])))
    return C(*steps, op=c.get("op"))


def selftest():
    scratch = os.environ.get("ORACLE_SAMPLE")
    failures = 0
    if scratch:
        register("oracle-sample", os.path.join(scratch, "sample.py"))
        print(extract(["oracle-sample"], force=True))
        t = Tree("oracle-sample")
        names = lambda c: sorted("%s@%d" % (t.node[k]["name"], t.node[k]["start_line"]) for k in t.select(c))  # noqa: E731
        cases = [
            (C(S(".call", pseudos=[P("in-scope", S(".class", "UserService"))])), ["execute@13", "execute@9"]),
            (C(S(".fn", pseudos=[P("in-scope", S(".class", "UserService"))])), ["__init__@5", "get_user@8", "safe_delete@11"]),
            (C(S(".fn", pseudos=[P("calls", "execute")])), ["get_user@8", "inner@24", "record@19", "safe_delete@11"]),
            (C(S(".fn", pseudos=[P("is-referenced")])), ["get_user@8", "inner@24", "outer@23"]),
            (C(S(".fn", pseudos=[P("exported")])), ["main@37", "outer@23", "unused_function@33"]),
            (C(S(".call", attrs=[["receiver", "=", "db"]])), ["execute@20", "execute@25"]),
            (C(S(".fn", pseudos=[P("is-called")])), ["get_user@8", "outer@23"]),
            (C(S(".call", pseudos=[P("called-by", "inner")])), ["execute@25"]),
            (C(S(".fn", pseudos=[P("has", S(".call", "execute")), P("not-has", S(".try"))])),
             ["get_user@8", "inner@24", "outer@23", "record@19"]),
            (C(S(".class", "UserService"), S(".fn", pseudos=[P("has", S(".call", "execute")), P("not-has", S(".try"))]), op=" "),
             ["get_user@8"]),
            (C(S(".fn", pseudos=[P("has", S(".call", attrs=[["receiver", "=", "db"]]))])),
             ["inner@24", "outer@23", "record@19"]),
            # pseudo-elements; the engine returned the same on this file (2026-09-15)
            (dict(C(S(".fn", "get_user")), element="callers"), ["main@37"]),
            (dict(C(S(".fn", "main")), element="callees"), ["UserService@38", "connect@38", "get_user@39", "outer@40"]),
        ]
        for c, want in cases:
            got = names(c)
            ok = got == want
            failures += not ok
            print("%s %-60s %s%s" % ("ok  " if ok else "FAIL", render(c), got, "" if ok else "  want %s" % want))
    # Regression: the selector-first pilot's engine-verified references.
    acc = os.path.join(HERE, "workspace", "sfgen", "pairs", "accepted-sf-p1.jsonl")
    sel = os.path.join(HERE, "workspace", "sfgen", "candidates", "selectors.jsonl")
    if os.path.exists(acc):
        structs = {r["id"]: r["struct"] for r in map(json.loads, open(sel))}
        rows = [json.loads(l) for l in open(acc)]
        fixtures = sorted({r["fixture"] for r in rows})
        print(extract(fixtures))
        trees = {fx: Tree(fx) for fx in fixtures}
        same = diff = 0
        for r in rows:
            c = from_sfgen(structs[r["id"]])
            if render(c) != r["css"]:
                print("render mismatch", render(c), r["css"])
                failures += 1
                continue
            if trees[r["fixture"]].digest(trees[r["fixture"]].select(c)) == r["reference"]["sha256"]:
                same += 1
            else:
                diff += 1
                if diff <= 5:
                    print("  differs from engine:", r["css"], r["fixture"])
        print("regression vs engine-verified sf-p1 references: %d same, %d differ" % (same, diff))
        failures += diff
    return failures


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "extract":
        for line in extract(sys.argv[2:]):
            print(line)
    elif len(sys.argv) > 1 and sys.argv[1] == "selftest":
        sys.exit(1 if selftest() else 0)
    else:
        print(__doc__)
