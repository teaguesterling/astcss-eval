"""v2: composition-aware. Real edits apply SEVERAL named ops at once, and wrap across lines.

v1 was line-based and single-label, so `const Opts &o)` -> `&o,\n const string &fmt)` looked
like an unclassifiable rewrite when it is plainly addParam. Fixes: join lines while paren
depth > 0 so a wrapped signature/call is one logical unit, and emit a SET of labels.
"""
import json, re, glob, collections

def logical(s):
    """Join physical lines while inside unbalanced parens/brackets -> logical lines."""
    out, buf, depth = [], "", 0
    for raw in (s or "").splitlines():
        l = raw.strip()
        if not l: continue
        buf = (buf + " " + l).strip() if buf else l
        depth += l.count("(") + l.count("[") - l.count(")") - l.count("]")
        if depth <= 0:
            out.append(re.sub(r"\s+", " ", buf)); buf, depth = "", 0
    if buf: out.append(re.sub(r"\s+", " ", buf))
    return out

def args_of(line):
    m = re.search(r"\(([^()]*(?:\([^()]*\)[^()]*)*)\)", line)
    if not m: return None
    inner = m.group(1).strip()
    return [a.strip() for a in re.split(r",(?![^(\[]*[)\]])", inner) if a.strip()] if inner else []

DEFN = re.compile(r"\b(def|fn|function|class|struct)\b|^\s*[\w:<>&*\s]+\s+\w+\s*\(")
COMMENT = re.compile(r'^(#|//|/\*|\*|"""|\'\'\'|--)')
IMPORT = re.compile(r"^(import|from .+ import|#include|use |require\()")
LITERAL = re.compile(r"[\"'][^\"']*[\"']|\b\d+(?:\.\d+)*\b")

def labels(old, new):
    o, n = logical(old), logical(new)
    so, sn = set(o), set(n)
    add = [l for l in n if l not in so]
    rem = [l for l in o if l not in sn]
    out = set()
    if not add and not rem: return {"whitespace_only"}
    if sorted(o) == sorted(n) and o != n: return {"reorder(move)"}
    if all(COMMENT.search(l) for l in add) and not rem: return {"comment_added"}
    if any(COMMENT.search(l) for l in add): out.add("comment_added")
    if any(IMPORT.search(l) for l in add): out.add("import_added")
    if any(re.search(r"^(try|except|catch|finally)\b", l) for l in add): out.add("try_wrap")
    # pair up near-identical lines to find in-place operations
    for a in add:
        best, score = None, 0.0
        for r in rem:
            common = len(set(a.split()) & set(r.split())) / max(len(set(a.split()) | set(r.split())), 1)
            if common > score: best, score = r, common
        if not best or score < 0.5: continue
        aa, ra = args_of(a), args_of(best)
        if aa is not None and ra is not None and aa != ra:
            if len(aa) == len(ra) + 1 and all(x in aa for x in ra):
                out.add("addParam" if DEFN.search(a) else "addArg")
            elif len(ra) == len(aa) + 1 and all(x in ra for x in aa):
                out.add("removeParam" if DEFN.search(a) else "removeArg")
        ca, cr = re.findall(r"(\w+)\s*\(", a), re.findall(r"(\w+)\s*\(", best)
        if len(ca) == len(cr) + 1 and all(x in ca for x in cr): out.add("wrap_expression")
        if LITERAL.sub("", a) == LITERAL.sub("", best) and a != best: out.add("literal_changed")
        if re.match(r"^(if|while|elif)\b", a) and re.match(r"^(if|while|elif)\b", best): out.add("condition_changed")
        if re.match(r"^return\b", a) and re.match(r"^return\b", best): out.add("return_changed")
    return out or {"rewrite"}

rows=[]
for f in glob.glob("workspace/editmine/edits-*.jsonl"):
    for l in open(f):
        l=l.strip()
        if l: rows.append(json.loads(l))
CODE={".py",".cpp",".hpp",".rs",".mjs",".js",".jsx",".ts",".sh",".sql",".c",".h",".go",".java"}
rep=[r for r in rows if r.get("kind")=="edit" and r.get("tool")=="Edit"
     and r.get("ext") in CODE and r.get("op")=="replace"]
lab=[labels(r.get("old"), r.get("new")) for r in rep]
flat=collections.Counter(x for s in lab for x in s)
explained=sum(1 for s in lab if s != {"rewrite"})
print("=== REPLACE, composition-aware (%d code records) ===" % len(rep))
print("  explained by >=1 named op: %d  (%.1f%%)   [v1 managed %.1f%%]"
      % (explained, 100.0*explained/len(rep), 100.0*(1785-1149)/1785))
for k,v in flat.most_common(16): print("   %-18s %5d  %5.1f%%" % (k,v,100.0*v/len(rep)))
print("\n  label-set sizes (composition):",
      dict(collections.Counter(len(s) for s in lab).most_common(5)))
print("  most common COMBINATIONS:")
for k,v in collections.Counter(tuple(sorted(s)) for s in lab if len(s)>1).most_common(6):
    print("    %-44s %4d" % (" + ".join(k)[:44], v))
