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
"""
import re

OPS = {"addComment", "addArg", "removeArg", "addParam", "removeParam", "wrapCall",
       "setCondition", "setReturn", "append", "prepend", "rename", "addImport", "wrapInTry"}
CLAUSES = {"on", "finally"}


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
    m = re.match(r"""^\$\(\s*(['"])(.+?)\1\s*\)\s*(\..+)$""", t, re.S)
    if not m:
        return None
    selector, rest = m.group(2), m.group(3)

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
    args, kwargs = [], {}
    for a in _split_args(raw):
        km = re.match(r"^(\w+)\s*[:=]\s*(.+)$", a, re.S)
        if km and km.group(1) in ("pos", "anchor", "code"):
            kwargs[km.group(1)] = _unquote(km.group(2))
        else:
            args.append(_unquote(a))
    clauses = [(n, [_unquote(x) for x in _split_args(r)]) for n, r in calls[1:]]
    return {"selector": selector, "op": op, "args": args,
            "kwargs": kwargs, "clauses": clauses}


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
    """Selector / op / args scored apart; clauses compared IN ORDER."""
    blank = {"selector": False, "op": False, "args": False, "all": False}
    if not got:
        return blank
    want = parse(task["call"])
    norm = lambda s: " ".join(str(s).split()).strip("'\"")
    sel = norm(got["selector"]) == norm(want["selector"])
    op = got["op"] == want["op"]
    args = ([norm(a) for a in got["args"]] == [norm(a) for a in want["args"]]
            and {k: norm(v) for k, v in got["kwargs"].items()}
                == {k: norm(v) for k, v in want["kwargs"].items()}
            and [(c, [norm(x) for x in a]) for c, a in got["clauses"]]
                == [(c, [norm(x) for x in a]) for c, a in want["clauses"]])
    return {"selector": sel, "op": op, "args": args, "all": sel and op and args}
