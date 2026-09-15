"""Audit pairs: does each request determine its selector's literal values without the fixture?

A pair passes the verifier when its selector selects the right nodes on its fixture. That
says nothing about whether the *request* carries what the selector needs: "functions whose
names start with cmd" verified as `.fn[name^="_cmd_"]` because the fixture's functions are
`_cmd_*`, but a model that cannot see the fixture learns that "starts with X" means `^="_X_"`.

Pass 1 (mechanical, a defect when it fires): a request that claims a prefix or suffix
("start with", "prefixed", "ends in", "suffix") against a `^=`/`$=` value. Per text:
  falsified   the claimed token is not a prefix (suffix) of the value: names that start with
              the value do not start with the claim ("start with cmd" vs "_cmd_")
  narrower    the value extends the claim: true of the result but underdetermined
              ("start with get" vs "get_")
  broader     the claim extends the value: the selector returns names the request excludes
              ("start with get_" vs "get")
  unfiltered  a positional claim with no ^= / $= filter in the selector
Pass 2 (inventory, triaged by hand): every name-like literal (#name, [attr op "v"], pseudo
arguments) and whether each request text contains it exactly, only after case/underscore
normalisation ("core"), or not at all ("absent": role-described or convention, e.g. "exit
the program" -> .call#exit).

    python3 audit_pairs.py [--out workspace/audit]      # every set, summary on stdout
"""
import collections
import glob
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

SETS = {
    "train": ["train/pairs/accepted-*.jsonl"],
    "sfgen": ["workspace/sfgen/pairs/accepted-*.jsonl"],
    "eval": ["pairs/accepted-*.jsonl", "pairs/pending-*.jsonl"],
    "eval_t5": ["eval_t5/pairs/accepted-*.jsonl", "eval_t5/pairs/pending-*.jsonl"],
}

ATTR_RE = re.compile(r'\[\s*([\w-]+)\s*([\^$*]?=)\s*(?:"([^"]*)"|([^\]\s"]+))\s*\]')
NAME_RE = re.compile(r'#([A-Za-z_$][\w$]*)')
PSEUDO_ARG_RE = re.compile(r':(calls|called-by|scope)\(\s*([A-Za-z_$][\w$]*)\s*\)')

WORD_TOKEN = {"underscore": "_", "underscores": "_", "dunder": "__", "double-underscore": "__"}
Q = r'["\'`“‘]?'
TOK = r'([\w$.-]+)'
LEAD = r'(?:an?\s+|the\s+)?(?:word\s+|prefix\s+|suffix\s+|string\s+|letters\s+|text\s+)?'
OBJ = r'(?:(?:their|its|the)\s+)?(?:names?\s+)?'  # "start their name with", "begin the name with"
PREFIX_PATTERNS = [
    re.compile(r'\b(?:start|starts|started|starting|begin|begins|beginning)\s+' + OBJ + r'with\s+' + LEAD + Q + r'((?:double[- ])?' + TOK[1:], re.I),
    re.compile(r'\bprefixed\s+(?:with\s+|by\s+)?' + LEAD + Q + TOK, re.I),
    re.compile(r'\bprefix\s+' + Q + TOK, re.I),
    re.compile(r'\b' + Q + TOK + Q + r'-prefix(?:ed|es)?\b', re.I),     # "cmd-prefixed"
    re.compile(r'\b' + Q + TOK + Q + r'\s+prefix(?:es)?\b', re.I),       # "the get_ prefix" (noun only)
    re.compile(r'\bleading\s+' + TOK, re.I),
]
SUFFIX_PATTERNS = [
    re.compile(r'\b(?:end|ends|ended|ending)\s+' + OBJ + r'(?:in|with)\s+' + LEAD + Q + TOK, re.I),
    re.compile(r'\bsuffixed\s+(?:with\s+|by\s+)?' + LEAD + Q + TOK, re.I),
    re.compile(r'\bsuffix\s+' + Q + TOK, re.I),
    re.compile(r'\b' + Q + TOK + Q + r'-suffix(?:ed|es)?\b', re.I),
    re.compile(r'\b' + Q + TOK + Q + r'\s+suffix(?:es)?\b', re.I),
    re.compile(r'\btrailing\s+' + TOK, re.I),
]
NOT_TOKENS = {"a", "an", "the", "with", "by", "in", "of", "and", "or", "that", "their", "its", "is",
              "names", "name", "word", "prefix", "suffix", "letter", "letters", "string", "text",
              "same", "common", "this", "some", "any", "functions", "function", "methods", "method",
              "classes", "class", "calls", "call", "types", "type", "variables", "definitions", "fields",
              "tables", "columns", "routines", "helpers", "commands", "identifiers", "their", "whose",
              "plural", "single", "double", "triple", "capital", "lowercase", "uppercase"}


def literals(css):
    """[(kind, attr, op, value)] for every name-like literal in a selector string."""
    out = []
    for m in ATTR_RE.finditer(css):
        attr, op, v = m.group(1), m.group(2), m.group(3) if m.group(3) is not None else m.group(4)
        if attr in ("params", "line"):
            continue
        out.append(("attr", attr, op, v))
    stripped = ATTR_RE.sub("", css)
    for m in NAME_RE.finditer(stripped):
        out.append(("name", "name", "=", m.group(1)))
    for m in PSEUDO_ARG_RE.finditer(stripped):
        out.append(("pseudo", m.group(1), "=", m.group(2)))
    return out


def _clean_token(t):
    t = t.strip("\"'`”’.,;:!?)(")
    low = t.lower()
    if low in WORD_TOKEN:
        return WORD_TOKEN[low]
    if low.startswith("double") and low[6:].lstrip("- ") in ("underscore", "underscores"):
        return "__"
    return t


def positional_claims(text):
    """[('prefix'|'suffix', token)] claimed by a request text."""
    claims = []
    for kind, pats in (("prefix", PREFIX_PATTERNS), ("suffix", SUFFIX_PATTERNS)):
        for pat in pats:
            for m in pat.finditer(text):
                tok = _clean_token(m.group(1))
                if tok and tok.lower() not in NOT_TOKENS:
                    claims.append((kind, tok))
    return sorted(set(claims))


def positional_findings(css, text):
    """Pass 1 for one request text: [{'verdict', 'kind', 'claim', 'value'}]; empty when consistent."""
    claims = positional_claims(text)
    if not claims:
        return []
    lits = literals(css)
    out = []
    exact = {kind for kind, claim in claims
             for (_, _, o, v) in lits if o == ("^=" if kind == "prefix" else "$=") and v.lower() == claim.lower()}
    for kind, claim in claims:
        if kind in exact:
            # "find next-prefixed invocations": the pattern also grabs "invocations"; one exact claim settles it
            continue
        op = "^=" if kind == "prefix" else "$="
        values = [v for (_, _, o, v) in lits if o == op]
        if not values:
            out.append({"verdict": "unfiltered", "kind": kind, "claim": claim, "value": None})
            continue
        c = claim.lower()
        best = None
        for v in values:
            vl = v.lower()
            if vl == c:
                best = None
                break
            has = vl.startswith(c) if kind == "prefix" else vl.endswith(c)
            ext = c.startswith(vl) if kind == "prefix" else c.endswith(vl)
            verdict = "narrower" if has else ("broader" if ext else "falsified")
            rank = {"narrower": 0, "broader": 1, "falsified": 2}[verdict]
            if best is None or rank < best[0]:
                best = (rank, {"verdict": verdict, "kind": kind, "claim": claim, "value": v})
        else:
            if best:
                out.append(best[1])
    return out


def _tokens(s):
    s = re.sub(r'([a-z0-9])([A-Z])', r'\1 \2', s)
    return [t for t in re.split(r'[^A-Za-z0-9$]+', s.lower()) if t]


INFLECTIONS = ("", "s", "es", "ed", "d", "ing", "er", "ers")


def _inflected(token, stem):
    """token is stem or an inflection of it: "sleeps"/"sleep", "parsing"/"parse". Not "reconciling"/"recon"."""
    for base in {stem, stem[:-1] if stem.endswith("e") else stem}:
        if token.startswith(base) and token[len(base):] in INFLECTIONS:
            return True
    return False


def presence(text, value):
    """'exact' (value as a whole word, case-insensitive), 'core' (its word tokens appear in order,
    last one possibly inflected), or 'absent'. Substrings don't count: "deletion" does not name del."""
    if value.strip("_") == "":
        return "exact" if re.search(r'underscore|dunder', text, re.I) or value in text else "absent"
    if re.search(r'(?<![A-Za-z0-9])%s(?:s|es)?(?![A-Za-z0-9])' % re.escape(value), text, re.I):
        return "exact"
    vt, tt = _tokens(value), _tokens(text)
    if not vt:
        return "absent"
    n = len(vt)
    for i in range(len(tt) - n + 1):
        if tt[i:i + n - 1] == vt[:-1] and _inflected(tt[i + n - 1], vt[-1]):
            return "core"
    return "absent"


# Names a role description does determine: a reader who can't see the fixture still gets them.
CONVENTIONAL = {"new", "__init__", "main", "execute", "count", "is_empty", "sqrt", "len", "print", "printf",
                "toString", "equals", "hashCode", "close", "open", "read", "write", "run", "map", "filter",
                "reduce", "forEach", "push", "append", "join", "split", "keys", "items", "values"}
_DEFINED = {}


def fixture_definitions(fixture, root=HERE):
    """Names of definition nodes (DEFINITION_* semantic types) in a fixture, from the oracle's node
    cache (workspace/oracle/<fixture>/nodes.csv, oracle.extract). Empty when the cache is missing."""
    if fixture not in _DEFINED:
        import csv
        path = os.path.join(root, "workspace", "oracle", fixture, "nodes.csv")
        names = set()
        if os.path.exists(path):
            csv.field_size_limit(10 ** 9)
            for r in csv.DictReader(open(path)):
                if r["sem"].startswith("DEFINITION_") and r["name"]:
                    names.add(r["name"])
        _DEFINED[fixture] = names
    return _DEFINED[fixture]


def request_reasons(css, text, fixture=None, root=HERE):
    """Why a request text does not determine its selector, as a gate (empty when it's fine):
    a prefix/suffix claim that isn't the filter's value; a name filter whose value isn't stated;
    a name defined in the fixture described only by its role; "immediately" worded against `~`;
    a request pointing outside itself ("that table")."""
    reasons = []
    for f in positional_findings(css, text):
        if f["verdict"] in ("falsified", "narrower", "broader"):
            reasons.append('says it %s with "%s" but the filter value is "%s"'
                           % ("starts" if f["kind"] == "prefix" else "ends", f["claim"], f["value"]))
    lits = literals(css)
    if not reasons:
        for kind, attr, op, v in lits:
            if kind == "attr" and attr == "name" and presence(text, v) != "exact":
                reasons.append('does not state the name filter %s"%s"' % (op, v))
    defined = fixture_definitions(fixture, root) if fixture else set()
    for kind, attr, op, v in lits:
        if kind == "name" and v in defined and v not in CONVENTIONAL and presence(text, v) == "absent":
            reasons.append("describes %s, defined in %s, only by its role" % (v, fixture))
    if "~" in _combinators(css) and IMMEDIATE_RE.search(text):
        reasons.append('says "%s" but ~ is any later sibling' % IMMEDIATE_RE.search(text).group(0))
    m = REFERENTIAL_RE.search(text)
    if m:
        reasons.append('points outside the request ("%s")' % m.group(0))
    return reasons


NEG_RE = re.compile(r"\b(?:no|not|without|never|lacks?|lacking|none|non|nothing|nobody|no ?one|nowhere|neither|nor|zero|"
                    r"except|excluding|other than|missing|doesn't|doesnt|don't|dont|isn't|aren't|unused|uncalled|"
                    r"unreferenced|free of|absent|outside|un\w+ed)\b", re.I)
IMMEDIATE_RE = re.compile(r'\b(?:immediately|directly|right (?:after|before|below|above|inside|under)|next to|adjacent|just (?:after|before))\b', re.I)
ORDER_RE = re.compile(r'\b(?:after|before|follow(?:s|ed|ing)?|preced(?:es|ed|ing)|later|earlier|sibling|subsequent|next)\b', re.I)
CHILD_RE = re.compile(r'\b(?:direct(?:ly)?|immediate(?:ly)?|top[- ]level|child(?:ren)?|right (?:inside|under|within|in))\b', re.I)
REFERENTIAL_RE = re.compile(r'\b(?:that|those|this|these|said|aforementioned)\s+(?:two\s+|one\s+)?'
                            r'(?:table|routine|function|class|type|service|helper|method|struct|letters?|'
                            r'block|object|wrapper|view|procedure)s?\b', re.I)  # "in this file" is scope, not a reference
NUM_WORDS = {"zero": 0, "no": 0, "one": 1, "single": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
             "seven": 7, "eight": 8, "nine": 9, "ten": 10}


def _combinators(css):
    """Top-level combinators of a selector (outside parentheses and attribute brackets)."""
    depth, ops, i = 0, [], 0
    s = re.sub(r'"[^"]*"', '""', css)
    while i < len(s):
        ch = s[i]
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        elif depth == 0 and ch in ">+~" and not s[i:i + 2] == "::":
            ops.append(ch)
        elif depth == 0 and ch == " " and s[i - 1:i] not in ">+~ " and s[i + 1:i + 2] not in ">+~ ":
            ops.append(" ")
        i += 1
    return ops


def structure_findings(css, text):
    """Pass 3 for one text: wording that contradicts the selector's structure (hand-reviewed)."""
    out = []
    has_not = ":not(" in css
    if has_not and not NEG_RE.search(text):
        out.append(("negation_missing", "selector negates, request has no negation word"))
    if not has_not and NEG_RE.search(text):
        out.append(("negation_extra", "request negates (%s), selector has no :not" % NEG_RE.search(text).group(0)))
    ops = _combinators(css)
    if "+" in ops and not IMMEDIATE_RE.search(text):
        out.append(("adjacent_unstated", "selector uses +, request has no immediacy word"))
    if "~" in ops and IMMEDIATE_RE.search(text):
        out.append(("sibling_immediate", "selector uses ~, request says %s" % IMMEDIATE_RE.search(text).group(0)))
    if not ({"+", "~"} & set(ops)) and ORDER_RE.search(text) and ops:
        out.append(("order_without_sibling", "request orders (%s), selector has no + or ~" % ORDER_RE.search(text).group(0)))
    if ">" in ops and not CHILD_RE.search(text):
        out.append(("child_unstated", "selector uses >, request has no direct/immediate/child word"))
    if " " in ops and ">" not in ops and CHILD_RE.search(text):
        out.append(("child_extra", "request says %s, selector uses the descendant combinator" % CHILD_RE.search(text).group(0)))
    for m in re.finditer(r'\[params\s*=\s*(\d+)\]', css):
        n = int(m.group(1))
        nums = {int(x) for x in re.findall(r'\b\d+\b', text)} | {v for w, v in NUM_WORDS.items() if re.search(r'\b%s\b' % w, text, re.I)}
        if n not in nums:
            out.append(("params_count", "selector [params=%d], request states %s" % (n, sorted(nums) or "no count")))
    m = REFERENTIAL_RE.search(text)
    if m:
        out.append(("referential", "request points outside itself: %r" % m.group(0)))
    return out


def load_set(name, root=HERE):
    rows = []
    for pat in SETS[name]:
        for f in sorted(glob.glob(os.path.join(root, pat))):
            for line in open(f):
                p = json.loads(line)
                rows.append(dict(p, _file=os.path.relpath(f, root)))
    return rows


def load_suite(out_dir, root=HERE):
    """Generated wordings joined to their selectors (gen_pairs word stage output)."""
    sel_path = os.path.join(root, out_dir, "candidates", "selectors.jsonl")
    words_path = os.path.join(root, out_dir, "words.json")
    if not (os.path.exists(sel_path) and os.path.exists(words_path)):
        return []
    words = json.load(open(words_path))
    rows = []
    for line in open(sel_path):
        c = json.loads(line)
        w = words.get(c["id"])
        if w and w.get("nl"):
            rows.append(dict(c, nl=w["nl"], paraphrases=w.get("paraphrases") or [], _file=os.path.join(out_dir, "words.json")))
    return rows


def audit_rows(rows, set_name):
    findings = []
    for p in rows:
        texts = [p["nl"]] + list(p.get("paraphrases") or [])
        lits = literals(p["css"])
        for k, tx in enumerate(texts):
            for f in positional_findings(p["css"], tx):
                findings.append(dict(f, set=set_name, id=p["id"], file=p["_file"], text_index=k, text=tx,
                                     css=p["css"], fixture=p.get("fixture"), tier=p.get("tier"), pass_=1))
            for rule, why in structure_findings(p["css"], tx):
                findings.append({"set": set_name, "id": p["id"], "file": p["_file"], "text_index": k, "text": tx,
                                 "css": p["css"], "fixture": p.get("fixture"), "tier": p.get("tier"), "pass_": 3,
                                 "rule": rule, "why": why})
        for kind, attr, op, v in lits:
            pres = [presence(tx, v) for tx in texts]
            if all(x == "exact" for x in pres):
                continue
            findings.append({"set": set_name, "id": p["id"], "file": p["_file"], "css": p["css"],
                             "fixture": p.get("fixture"), "tier": p.get("tier"), "pass_": 2,
                             "literal": {"kind": kind, "attr": attr, "op": op, "value": v},
                             "presence": pres, "texts": texts})
    return findings


def main(argv):
    out = "workspace/audit"
    if "--out" in argv:
        out = argv[argv.index("--out") + 1]
    os.makedirs(os.path.join(HERE, out), exist_ok=True)
    all_sets = {n: load_set(n) for n in SETS}
    for d in ("workspace/suite1", "workspace/siblings1", "workspace/callgraph1"):
        rows = load_suite(d)
        if rows:
            all_sets[os.path.basename(d)] = rows
    summary = []
    for name, rows in all_sets.items():
        fs = audit_rows(rows, name)
        with open(os.path.join(HERE, out, "%s.jsonl" % name), "w") as fh:
            for f in fs:
                fh.write(json.dumps(f, ensure_ascii=False) + "\n")
        p1 = [f for f in fs if f["pass_"] == 1]
        v1 = collections.Counter(f["verdict"] for f in p1)
        pairs1 = {f["id"] for f in p1 if f["verdict"] in ("falsified", "broader", "unfiltered")}
        p2 = [f for f in fs if f["pass_"] == 2]
        absent_all = {f["id"] for f in p2 if all(x == "absent" for x in f["presence"])}
        absent_some = {f["id"] for f in p2 if any(x == "absent" for x in f["presence"])}
        core_only = {f["id"] for f in p2 if "absent" not in f["presence"]}
        texts = sum(1 + len(r.get("paraphrases") or []) for r in rows)
        v3 = collections.Counter(f["rule"] for f in fs if f["pass_"] == 3)
        summary.append((name, len(rows), texts, dict(v1), len(pairs1), len(core_only), len(absent_some), len(absent_all),
                        dict(v3)))
    print("| set | pairs | texts | pass 1 texts by verdict | pairs with a falsified/broader/unfiltered text "
          "| literal only after normalising | literal absent from some text | from every text | pass 3 texts by rule |")
    print("|---|---|---|---|---|---|---|---|---|")
    for s in summary:
        print("| %s | %d | %d | %s | %d | %d | %d | %d | %s |" % s)


if __name__ == "__main__":
    main(sys.argv[1:])
