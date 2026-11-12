"""Parse and score mutator-grammar answers.

    $('<selector>').<op>(<args>)[.<op>(<args>)]*[.on(exc, body)]*[.finally(body)]

Three buckets, as in the surface study: ok / wrong_surface / malformed. "Malformed" means the
syntax defeated the model; "wrong surface" means it answered in a different form entirely (raw
astcss, a sed command, JSON) -- different failures, different fixes, and collapsing them hides
which one is happening.

Scored per part -- selector / op / args -- because the argument is partly transcribed from the
request, so a single combined number is inflated relative to the selector evals.

Clause ORDER is load-bearing: .on("KeyError") before .on("Exception") is a different program, so
clauses compare as an ordered list, never as a set.

VARIABLES ARE BARE, LITERALS ARE QUOTED. One rule, both positions:

    $('.fn#calc').replaceWith(new_code)    bare   -> a variable, supplied by the caller
    $('.call#c').addArg("retries=3")       quoted -> a literal
    $(target).wrapInTry()                  bare selector, supplied by the caller

There is no `params.` prefix and no ${...} interpolation. An argument is a variable if it is a
bare identifier and a literal otherwise, which the parser can decide on its own -- so a call
referencing an undeclared variable is caught at PARSE time, with no payload and nothing executed.
`check_variables` does that against the names the prompt declared on its `Variables:` line.

Quoting is therefore load-bearing and must survive parsing. It previously did not: args were
unquoted the moment they were split, so `"foo"` and `foo` became the same string and a model
inlining a literal where a variable was required scored as correct. `arg_kinds` keeps the
distinction; `args` still holds the unquoted values so existing callers are unaffected.
"""
import re

OPS = {"addComment", "addArg", "removeArg", "addParam", "removeParam", "wrapCall",
       "setCondition", "setReturn", "append", "prepend", "rename", "addImport", "wrapInTry"}
CLAUSES = {"on", "finally"}

#: A bare identifier in argument or selector position names a caller-supplied variable.
_IDENT = re.compile(r"^[A-Za-z_]\w*$")


def _kind(raw):
    """'variable' for a bare identifier, 'literal' otherwise. Decided on the RAW text,
    before any unquoting -- that is the only place the distinction still exists."""
    return "variable" if _IDENT.match(raw.strip()) else "literal"


def _split_args(s):
    """Quote-aware comma split that also keeps `name: value` pairs intact."""
    out, cur, q, esc, depth = [], [], None, False, 0
    for ch in s:
        if esc:
            cur.append(ch); esc = False; continue
        if ch == "\\":
            cur.append(ch); esc = True; continue
        if q:
            cur.append(ch)
            if ch == q: q = None
            continue
        if ch in "\"'":
            q = ch; cur.append(ch); continue
        if ch in "([{": depth += 1
        elif ch in ")]}": depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(cur).strip()); cur = []; continue
        cur.append(ch)
    tail = "".join(cur).strip()
    if tail: out.append(tail)
    return out


def _unquote(v):
    v = v.strip()
    if len(v) >= 2 and v[0] in "\"'" and v[-1] == v[0]:
        return v[1:-1]
    return v


def parse(text):
    """-> {selector, op, args, kwargs, clauses:[(kind, [args])]} or None."""
    t = (text or "").strip()
    m = re.match(r"^```[a-z]*\s*(.*?)\s*```$", t, re.S)
    if m: t = m.group(1).strip()
    t = t.strip().rstrip(";")
    # The selector is quoted for a literal and bare for a caller-supplied one.
    m = re.match(r"""^\$\(\s*(['"])(.+?)\1\s*\)\s*(\..+)$""", t, re.S)
    if m:
        selector, rest, selector_kind = m.group(2), m.group(3), "literal"
    else:
        m = re.match(r"""^\$\(\s*([A-Za-z_]\w*)\s*\)\s*(\..+)$""", t, re.S)
        if not m:
            return None
        selector, rest, selector_kind = m.group(1), m.group(2), "variable"

    calls = []
    pos = 0
    while pos < len(rest):
        cm = re.match(r"\.\s*(\w+)\s*\(", rest[pos:])
        if not cm:
            return None
        name = cm.group(1)
        i = pos + cm.end()
        depth, q, esc, start = 1, None, False, i
        while i < len(rest) and depth:
            ch = rest[i]
            if esc: esc = False
            elif ch == "\\": esc = True
            elif q:
                if ch == q: q = None
            elif ch in "\"'": q = ch
            elif ch == "(": depth += 1
            elif ch == ")": depth -= 1
            i += 1
        if depth:
            return None
        calls.append((name, rest[start:i - 1]))
        pos = i
        while pos < len(rest) and rest[pos].isspace(): pos += 1
    if not calls:
        return None

    op, raw = calls[0]
    args, kwargs, arg_kinds, kwarg_kinds = [], {}, [], {}
    for a in _split_args(raw):
        km = re.match(r"^(\w+)\s*[:=]\s*(.+)$", a, re.S)
        if km and km.group(1) in ("pos", "anchor", "code"):
            kwargs[km.group(1)] = _unquote(km.group(2))
            kwarg_kinds[km.group(1)] = _kind(km.group(2))
        else:
            args.append(_unquote(a))
            arg_kinds.append(_kind(a))
    clause_raw = [(n, _split_args(r)) for n, r in calls[1:]]
    clauses = [(n, [_unquote(x) for x in xs]) for n, xs in clause_raw]
    clause_kinds = [(n, [_kind(x) for x in xs]) for n, xs in clause_raw]

    used = {s for s, k in [(selector, selector_kind)] if k == "variable"}
    used |= {a for a, k in zip(args, arg_kinds) if k == "variable"}
    used |= {v for k_, v in kwargs.items() if kwarg_kinds.get(k_) == "variable"}
    for (_, xs), (_, ks) in zip(clauses, clause_kinds):
        used |= {x for x, k in zip(xs, ks) if k == "variable"}

    return {"selector": selector, "op": op, "args": args,
            "kwargs": kwargs, "clauses": clauses,
            "selector_kind": selector_kind, "arg_kinds": arg_kinds,
            "kwarg_kinds": kwarg_kinds, "clause_kinds": clause_kinds,
            "variables": used}


def check_variables(got, declared):
    """Static check against the prompt's `Variables:` line. -> (ok, problems).

    Nothing is executed and no payload is needed: a bare identifier is a variable by
    construction, so an undeclared reference is a parse-time error. Declared-but-unused is
    reported too -- it means the prompt offered something the answer ignored, usually by
    inlining a literal where the caller meant to supply the value.
    """
    if not got:
        return False, ["unparseable"]
    declared = set(declared or ())
    used = set(got.get("variables") or ())
    problems = []
    for name in sorted(used - declared):
        problems.append("uses undeclared variable %r" % name)
    for name in sorted(declared - used):
        problems.append("declared but unused: %r" % name)
    return not problems, problems


def declared_in(request):
    """Pull the names off a request's trailing `Variables: a, b` line. -> [names]."""
    m = re.search(r"(?im)^\s*variables\s*:\s*(.+?)\s*$", request or "")
    if not m:
        m = re.search(r"(?i)\bvariables\s*:\s*([A-Za-z_][\w,\s]*)$", (request or "").strip())
    if not m:
        return []
    return [p.strip() for p in re.split(r"[,\s]+", m.group(1)) if p.strip()]


def judge(text):
    """ok / wrong_surface / malformed."""
    got = parse(text)
    if got and got["op"] in OPS and all(c in CLAUSES for c, _ in got["clauses"]):
        return "ok", got
    t = (text or "").strip()
    if got:                                   # parsed but unknown op or clause
        return "malformed", got
    if re.match(r"^\s*[.#]\w", t) or "{" in t or t.startswith(("sed ", "find ", "$(")):
        return "wrong_surface", None          # bare astcss, PSS, a shell command
    return "malformed", None


def score(task, got):
    """Selector / op / args scored apart; clauses compared IN ORDER.

    A literal and a variable of the same name are NOT the same answer: inlining `new_code`
    where the caller supplies it is a different program from referencing it. `norm` no longer
    strips quotes, so the kinds are compared alongside the values.
    """
    blank = {"selector": False, "op": False, "args": False, "all": False}
    if not got:
        return blank
    want = parse(task["call"])
    norm = lambda s: " ".join(str(s).split())
    sel = (norm(got["selector"]) == norm(want["selector"])
           and got.get("selector_kind") == want.get("selector_kind"))
    op = got["op"] == want["op"]
    args = ([norm(a) for a in got["args"]] == [norm(a) for a in want["args"]]
            and got.get("arg_kinds") == want.get("arg_kinds")
            and {k: norm(v) for k, v in got["kwargs"].items()}
                == {k: norm(v) for k, v in want["kwargs"].items()}
            and got.get("kwarg_kinds") == want.get("kwarg_kinds")
            and [(c, [norm(x) for x in a]) for c, a in got["clauses"]]
                == [(c, [norm(x) for x in a]) for c, a in want["clauses"]]
            and got.get("clause_kinds") == want.get("clause_kinds"))
    return {"selector": sel, "op": op, "args": args, "all": sel and op and args}
