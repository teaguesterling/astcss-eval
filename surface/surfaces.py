"""Five candidate output surfaces for astcss mutations, and a judge for each.

The study question: a mutation is selector + operation + arguments. The SELECTOR part is
identical in every surface -- only the wrapper syntax changes -- so any difference between
arms is attributable to the surface and not to the selector vocabulary.

Card construction (parity): every arm gets the same card body -- card_v1c.md's validated
selector vocabulary with its selector-only instruction replaced -- plus the same operation
table, plus a SURFACE BLOCK of fixed shape (one syntax line, two worked examples). The only
text that differs between arms is that block. Hand-writing five whole cards would make the
arms differ in information content and the study would measure card quality instead.

Judging is three-bucket, not two. "Malformed" (the syntax is hard) and "wrong surface"
(the card lost -- the model emitted a DIFFERENT surface, most likely JSON) are different
failures with different fixes, so every output is parsed by all five parsers: if its own
parser fails and another succeeds, that is wrong_surface.

Each surface also has an unrepresentability constraint, the way pluckit's argv grammar
steals any argument spelling an op name. Finding each surface's is part of the result;
the ones known before running are recorded in LIMITS below.

Surface D is NOT invented here. PSS is a real language in this ecosystem -- specified in
pluckit's docs/superpowers/specs/2026-04-10-ast-css-viewer-design.md, implemented in
pluckit/pluckins/viewer.py, and already evaluated for SELECTOR generation in squackit's
scripts/selector_eval.py, where every model from 0.5b up produced a valid selector 100% of
the time ("constrain the output space, don't grow the model"). That study compared selectors
against a Python tool API; it never compared surfaces for MUTATION, which is what this does.

D's encoding was chosen against the real parser, not guessed. Measured behaviour:
  * `{ remove; }` -- a declaration with no value -- is SILENTLY DROPPED, leaving a bare
    selector, and a bare selector means `show: body`. A mutation would silently become a
    view. So the operation can never be a valueless key.
  * declaration KEYS are lowercased (insertBefore -> insertbefore) but VALUES keep their
    case, so the operation name has to live in a value.
  * values are single (grammar: identifier | number | quoted_string); a comma-separated
    value mangles. Multiple arguments must be multiple declarations.
  * `partition(':')` splits on the first colon only and then strips quotes, so a value
    containing a colon ("try:", "except Exception: pass") round-trips fine.
Hence: op as a value, arguments as named properties -- uniform across arity, case-preserving,
colon-safe, and incapable of degrading into a view.

PSS also has a path to being engine-native: ast_select_rules / ast_select_list exist in
sitting_duck's bump-duckdb-v1.5-variegata tree, gated on an upstream DuckDB bind-time fix.
"""
import json
import re

OPS = {
    "remove": 0, "unwrap": 0,
    "rename": 1, "addParam": 1, "removeParam": 1, "addArg": 1, "removeArg": 1,
    "prepend": 1, "append": 1, "patch": 1,
    "replaceWith": 2, "wrap": 2, "insertBefore": 2, "insertAfter": 2,
}

#: PSS (surface D) names each argument instead of positioning it, because a PSS declaration
#: takes exactly one value. Keys are lowercase -- the parser lowercases them anyway.
PSS_ARGKEYS = {
    "remove": [], "unwrap": [],
    "rename": ["to"], "addParam": ["param"], "removeParam": ["param"],
    "addArg": ["arg"], "removeArg": ["arg"],
    "prepend": ["code"], "append": ["code"], "patch": ["content"],
    "replaceWith": ["from", "to"], "wrap": ["before", "after"],
    "insertBefore": ["anchor", "code"], "insertAfter": ["anchor", "code"],
}

SHARED_HEADER = """\
You translate a developer's plain-English request into ONE mutation over a Python code tree.
A mutation has three parts: a SELECTOR (which nodes), an OPERATION (what to do to them), and
the operation's ARGUMENTS. Reply with the mutation only: one line, no explanation, no backticks.
"""

SHARED_OPS = """
OPERATIONS (argument count in brackets)
  remove [0]            delete the matched nodes
  unwrap [0]            drop the node's first and last line, dedent the rest
  rename [1]            new name
  addParam [1]          parameter to add to a function definition
  removeParam [1]       parameter name to drop from a function definition
  addArg [1]            argument to add to a call
  removeArg [1]         keyword-argument name to drop from a call
  prepend [1]           code inserted at the TOP of the node's body
  append [1]            code inserted at the BOTTOM of the node's body
  replaceWith [2]       old text, new text (replaced inside the node)
  wrap [2]              code placed before the node, code placed after it
  insertBefore [2]      a SELECTOR naming an inner anchor, then code to insert before it
  insertAfter [2]       a SELECTOR naming an inner anchor, then code to insert after it
"""

# --- surface blocks: fixed shape -- one syntax line, two worked examples -------------
BLOCKS = {
    "A_jquery": """
WRITE IT AS A JQUERY-STYLE CHAIN: $('<selector>').<operation>('<arg>', '<arg>')
  rename the helper function to run      ->  $('.fn#helper').rename('run')
  in save, add x = 1 before the return   ->  $('.fn#save').insertBefore('.jump', 'x = 1')
""",
    "B_argv": """
WRITE IT AS A COMMAND LINE: find <selector> <operation> <arg> <arg>
  rename the helper function to run      ->  find .fn#helper rename run
  in save, add x = 1 before the return   ->  find .fn#save insertBefore .jump "x = 1"
""",
    "C_json": """
WRITE IT AS JSON: {"select": "<selector>", "op": "<operation>", "args": ["<arg>"]}
  rename the helper function to run      ->  {"select": ".fn#helper", "op": "rename", "args": ["run"]}
  in save, add x = 1 before the return   ->  {"select": ".fn#save", "op": "insertBefore", "args": [".jump", "x = 1"]}
""",
    "D_pss": """
WRITE IT AS A PSS RULE: <selector> { op: <operation>; <name>: <value>; }
  rename the helper function to run      ->  .fn#helper { op: rename; to: run; }
  in save, add x = 1 before the return   ->  .fn#save { op: insertBefore; anchor: .jump; code: "x = 1"; }
""",
    "E_prefix": """
WRITE IT AS A FUNCTION CALL: <operation>('<selector>', '<arg>', '<arg>')
  rename the helper function to run      ->  rename('.fn#helper', 'run')
  in save, add x = 1 before the return   ->  insertBefore('.fn#save', '.jump', 'x = 1')
""",
}

#: Known-before-running representability limits. Every surface has one; part of the result
#: is discovering the rest.
LIMITS = {
    "A_jquery": "an argument containing an unescaped single quote needs escaping",
    "B_argv": "FATAL WITHOUT THE OP-BOUNDARY RULE: an astcss combinator selector contains a "
              "space (.fn#a .call#b), so whitespace-splitting shreds the selector itself. Also: "
              "multi-word arguments need quoting, and an argument spelling an op name is stolen "
              "(pluckit _KNOWN_OPS)",
    "C_json": "none known -- JSON quotes everything",
    "D_pss": "a value containing ';' or '}' must be quoted, and a valueless declaration "
             "({ remove; }) is silently dropped into a bare selector -- which PSS reads as "
             "'show: body', turning a mutation into a view. Avoided by putting the op in a value",
    "E_prefix": "same quoting constraint as A",
}


def build_card(card_body, surface):
    """Shared header + shared vocabulary + shared op table + this surface's block."""
    return SHARED_HEADER + card_body + SHARED_OPS + BLOCKS[surface]


def strip_selector_instruction(card_v1c_text):
    """card_v1c.md opens with a two-line 'reply with the selector only' instruction that
    contradicts a mutation task. Keep everything from the first vocabulary heading on."""
    i = card_v1c_text.find("SEMANTIC CLASSES")
    return card_v1c_text[i:] if i > 0 else card_v1c_text


# --- canonical rendering (also supplies few-shot examples and the reference string) ---
def render(surface, selector, op, args):
    if surface == "A_jquery":
        inner = ", ".join("'%s'" % a for a in args)
        return "$('%s').%s(%s)" % (selector, op, inner)
    if surface == "B_argv":
        quoted = ['"%s"' % a if (" " in a or not a) else a for a in args]
        return " ".join(["find", selector, op] + quoted)
    if surface == "C_json":
        return json.dumps({"select": selector, "op": op, "args": list(args)})
    if surface == "D_pss":
        decls = ["op: %s" % op]
        for k, v in zip(PSS_ARGKEYS.get(op, []), args):
            decls.append("%s: %s" % (k, _pss_value(v)))
        return "%s { %s; }" % (selector, "; ".join(decls))
    if surface == "E_prefix":
        inner = ", ".join("'%s'" % a for a in [selector] + list(args))
        return "%s(%s)" % (op, inner)
    raise KeyError(surface)


# --- parsers: each returns dict(selector, op, args) or None ---------------------------
def _split_quoted(s):
    """Comma-separated, quote-aware argument splitter for A/D/E."""
    out, cur, q, esc = [], [], None, False
    for ch in s:
        if esc:
            cur.append(ch); esc = False; continue
        if ch == "\\":
            esc = True; continue
        if q:
            if ch == q: q = None
            else: cur.append(ch)
        elif ch in "\"'":
            q = ch
        elif ch == ",":
            out.append("".join(cur).strip()); cur = []
        else:
            cur.append(ch)
    tail = "".join(cur).strip()
    if tail or out:
        out.append(tail)
    return [a for a in out if a != ""]


def parse_A(text):
    m = re.match(r"""^\s*\$\(\s*['"]([^'"]+)['"]\s*\)\s*\.\s*(\w+)\s*\((.*)\)\s*;?\s*$""", text, re.S)
    if not m:
        return None
    return {"selector": m.group(1), "op": m.group(2), "args": _split_quoted(m.group(3))}


def parse_E(text):
    m = re.match(r"""^\s*(\w+)\s*\((.*)\)\s*;?\s*$""", text, re.S)
    if not m:
        return None
    parts = _split_quoted(m.group(2))
    if not parts:
        return None
    return {"selector": parts[0], "op": m.group(1), "args": parts[1:]}


def parse_C(text):
    try:
        d = json.loads(text.strip())
    except Exception:
        return None
    if not isinstance(d, dict):
        return None
    sel = d.get("select") or d.get("selector")
    op = d.get("op") or d.get("operation")
    if not sel or not op:
        return None
    args = d.get("args", [])
    if isinstance(args, str):
        args = [args]
    return {"selector": str(sel), "op": str(op), "args": [str(a) for a in args]}


def _pss_value(v):
    """Bare where PSS would write it bare (identifier/number/selector), quoted otherwise.
    A ';' or '}' would end the declaration or the block, so those always force quotes."""
    if v and re.match(r"^[A-Za-z_.#][\w.#\-]*$", v) and not re.search(r"[;}]", v):
        return v
    return '"%s"' % v.replace('"', '\\"')


def _pss_rules(text):
    """Parse with pluckit's OWN viewer parser when it is importable, so surface D is judged
    by the real implementation rather than by a regex that agrees with itself. Falls back to
    an equivalent local parse when pluckit is not on the path."""
    try:
        import warnings
        from pluckit.pluckins.viewer import parse_viewer_query
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            return [(r.selector, dict(r.declarations)) for r in parse_viewer_query(text)]
    except Exception:
        pass
    m = re.match(r"^\s*(.+?)\s*\{(.*)\}\s*$", text, re.S)
    if not m:
        return []
    decls = {}
    for item in re.split(r";(?=(?:[^\"']*[\"'][^\"']*[\"'])*[^\"']*$)", m.group(2)):
        item = item.strip()
        if ":" not in item:
            continue
        k, _, v = item.partition(":")
        v = v.strip()
        if len(v) >= 2 and v[0] in "\"'" and v[-1] == v[0]:
            v = v[1:-1]
        decls[k.strip().lower()] = v
    return [(m.group(1).strip(), decls)]


def parse_D(text):
    rules = _pss_rules(text)
    if len(rules) != 1:
        return None
    selector, decls = rules[0]
    op = decls.get("op")
    if not op or not selector:
        return None
    keys = PSS_ARGKEYS.get(op)
    if keys is None:                       # unknown op: hand it back so the scorer marks it
        return {"selector": selector, "op": op, "args": []}
    return {"selector": selector, "op": op, "args": [decls[k] for k in keys if k in decls]}


def parse_B(text):
    """pluckit's actual rule: the first token spelling a known op ends the selector.

    This matters because an astcss selector CONTAINS SPACES whenever it uses a combinator
    (`.fn#bulk_import .call#print`), so a naive whitespace split shreds the selector itself --
    the single worst representability problem of any surface here, and the reason B needs the
    op-boundary rule rather than fixed token positions. shlex runs first so a quoted
    multi-word argument (`"self.url = None"`) survives as one token.

    Note this judge is MORE forgiving than pluckit's own `Chain.from_argv`, which would split
    `rename replace` into two steps; here only a token before the first op can be stolen, and
    selectors never spell bare op names. B's score is therefore an upper bound on what
    pluckit would actually accept."""
    import shlex
    text = text.strip()
    try:
        toks = shlex.split(text)
    except ValueError:
        toks = text.split()
    if toks and toks[0] == "find":
        toks = toks[1:]
    idx = next((i for i, t in enumerate(toks) if t in OPS), None)
    if idx is None or idx == 0:
        return None
    return {"selector": " ".join(toks[:idx]), "op": toks[idx], "args": toks[idx + 1:]}


PARSERS = {"A_jquery": parse_A, "B_argv": parse_B, "C_json": parse_C,
           "D_pss": parse_D, "E_prefix": parse_E}


def judge(surface, text):
    """Three buckets: ok / wrong_surface / malformed."""
    text = (text or "").strip()
    # models like to fence things even when told not to
    fence = re.match(r"^```[a-z]*\s*(.*?)\s*```$", text, re.S)
    if fence:
        text = fence.group(1).strip()
    own = PARSERS[surface](text)
    if own:
        return "ok", own
    for other, p in PARSERS.items():
        if other == surface:
            continue
        # B is permissive enough to swallow prose; only count it as a competing
        # surface when it is not the one being judged AND it yields a known op.
        got = p(text)
        if got and got.get("op") in OPS:
            return "wrong_surface", got
    return "malformed", None


def score(task, got):
    """Selector / op / args scored separately -- the argument is partly transcription,
    so a combined number would be inflated relative to the selector tiers."""
    if not got:
        return {"selector": False, "op": False, "args": False, "all": False}
    def norm(s):
        return re.sub(r"\s+", " ", str(s).strip().strip("'\""))
    sel = norm(got["selector"]) == norm(task["selector"])
    op = norm(got["op"]) == norm(task["op"])
    args = [norm(a) for a in got["args"]] == [norm(a) for a in task["args"]]
    return {"selector": sel, "op": op, "args": args, "all": sel and op and args}
