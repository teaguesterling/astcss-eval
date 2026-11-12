"""Break `replace` and `append` into sub-operations that could stand alone in a mutation API.

They are 79% of all edits and currently say nothing. The question is whether that mass
decomposes into nameable operations or is irreducibly "rewrite this block".
Detectors run most-specific-first; the residual bucket is the honest answer about how much
does NOT reduce to an operation.
"""
import json, re, collections, sys, glob

def lines(s): return [l.rstrip() for l in (s or "").splitlines() if l.strip()]
def strip_all(ls): return [l.strip() for l in ls]

RE = {
 "try":      re.compile(r"^\s*(try|except|catch|finally|rescue)\b"),
 "guard":    re.compile(r"^\s*(if|unless)\b.*\b(return|raise|throw|continue|break|exit)\b"),
 "ret":      re.compile(r"^\s*return\b|^\s*yield\b"),
 "cond":     re.compile(r"^\s*(if|elif|else if|while|switch|match)\b"),
 "import":   re.compile(r"^\s*(import|from .+ import|#include|use |require\()"),
 "comment":  re.compile(r'^\s*(#|//|/\*|\*|"""|\'\'\')'),
 "decor":    re.compile(r"^\s*@\w"),
 "defn":     re.compile(r"^\s*(def|fn|function|class|struct|impl)\b|^\s*\w[\w:<>\s\*&]*\s+\w+\s*\([^;]*\)\s*\{?\s*$"),
 "assert":   re.compile(r"\b(assert|EXPECT_|ASSERT_|expect\(|should\b)"),
 "log":      re.compile(r"\b(print|log(ger)?\.|console\.(log|error)|echo)\b"),
 "field":    re.compile(r"^\s*[\w\"'\[]+\s*[:=]\s*.+,\s*$"),
 "annot":    re.compile(r"(->\s*[A-Za-z\[\"']|:\s*(int|str|bool|float|List|Dict|Optional|Any|[A-Z]\w+)\s*[=,)]?\s*$)"),
 "call":     re.compile(r"\w+\s*\("),
}
KW = re.compile(r"(\w+)\s*=")

def sub_replace(old, new):
    o, n = lines(old), lines(new)
    so, sn = strip_all(o), strip_all(n)
    if not o or not n: return "degenerate"
    if sorted(so) == sorted(sn) and so != sn:            return "reorder(move)"
    if so == sn and o != n:                              return "indentation_only"
    add = [l for l in sn if l not in so]
    rem = [l for l in so if l not in sn]
    if not add and not rem:                              return "whitespace_only"
    # wrapping: everything old survives, plus a try/except scaffold
    if all(l in sn for l in so) and any(RE["try"].search(l) for l in add):  return "try_wrap"
    if all(l in sn for l in so) and any(RE["guard"].search(l) for l in add): return "guard_added"
    if all(l in sn for l in so):
        if any(RE["import"].search(l) for l in add):     return "import_added"
        if any(RE["decor"].search(l) for l in add):      return "decorator_added"
        if any(RE["comment"].search(l) for l in add):    return "comment_added"
        if any(RE["log"].search(l) for l in add):        return "logging_added"
        if any(RE["assert"].search(l) for l in add):     return "assertion_added"
        return "block_inserted"
    if all(RE["comment"].search(l) for l in add+rem):    return "comment_only"
    if all(RE["import"].search(l) for l in add+rem):     return "import_changed"
    if len(add) == 1 and len(rem) == 1:
        a, r = add[0], rem[0]
        if RE["cond"].search(a) and RE["cond"].search(r):   return "condition_changed"
        if RE["ret"].search(a) and RE["ret"].search(r):     return "return_changed"
        ka, kr = set(KW.findall(a)), set(KW.findall(r))
        if ka - kr and not (kr - ka):                       return "kwarg_added"
        if kr - ka and not (ka - kr):                       return "kwarg_removed"
        if RE["annot"].search(a) and not RE["annot"].search(r): return "annotation_added"
        ca = re.findall(r"(\w+)\s*\(", a); cr = re.findall(r"(\w+)\s*\(", r)
        if ca and cr and ca != cr and len(ca) == len(cr):   return "call_target_swap"
        if re.sub(r"[\"'][^\"']*[\"']|\b\d+\b", "", a) == re.sub(r"[\"'][^\"']*[\"']|\b\d+\b", "", r):
            return "literal_changed"
        return "line_rewrite"
    return "rewrite"

def sub_append(old, new):
    o, n = lines(old), lines(new)
    add = [l for l in strip_all(n) if l not in strip_all(o)]
    if not add: return "degenerate"
    a = " ".join(add)
    if all(RE["comment"].search(l) for l in add):     return "doc/comment"
    if any(RE["import"].search(l) for l in add):      return "import"
    if any(RE["defn"].search(l) for l in add):        return "function/class"
    if any(RE["cond"].search(l) for l in add):        return "branch"
    if any(RE["ret"].search(l) for l in add):         return "return"
    if any(RE["assert"].search(l) for l in add):      return "assertion"
    if any(RE["log"].search(l) for l in add):         return "logging"
    if all(RE["field"].search(l) for l in add):       return "collection_field"
    if RE["call"].search(a):                          return "call_statement"
    return "statement"

rows=[]
for f in glob.glob("workspace/editmine/edits-*.jsonl"):
    for l in open(f):
        l=l.strip()
        if l: rows.append(json.loads(l))
ed=[r for r in rows if r.get("kind")=="edit" and r.get("tool")=="Edit"]
CODE={".py",".cpp",".hpp",".rs",".mjs",".js",".jsx",".ts",".sh",".sql",".c",".h",".go",".java"}
code=[r for r in ed if r.get("ext") in CODE]
print("corpus: %d edits, %d in code files\n" % (len(ed), len(code)))

for op, fn in (("replace", sub_replace), ("append", sub_append)):
    sub=[r for r in code if r.get("op")==op]
    c=collections.Counter(fn(r.get("old"), r.get("new")) for r in sub)
    print("=== %s -> sub-operations (%d records in code files) ===" % (op.upper(), len(sub)))
    for k,v in c.most_common():
        print("   %-20s %5d  %5.1f%%" % (k, v, 100.0*v/max(len(sub),1)))
    print()
