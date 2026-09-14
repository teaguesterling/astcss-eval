"""Build the per-language vocabulary cards for training prompts.

usage: make_cards.py <audit-inventory-dir> <type-maps.json>

Python's card is card_v1c.md byte for byte: training prompts must match the eval's.
Every other language gets card_v1c's structure and examples, with:
  - the language named in the first sentence,
  - each semantic class annotated with the node types it actually matched in that
    language's fixtures (from the audit), and classes that matched nothing dropped,
  - a node-type list of the language's most frequent definition / flow / error /
    import types in its fixtures (kinds from ast_type_map),
  - no [params=N] line (only verified on Python).
Classes with known engine defects (operators #131, .bool #132, .comment #134) keep
their card line, as in the eval card, but drafting agents are told not to use them.
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DISPLAY = {"python": "Python", "rust": "Rust", "javascript": "JavaScript", "typescript": "TypeScript",
           "cpp": "C++", "c": "C", "sql": "SQL", "bash": "Bash", "java": "Java", "go": "Go"}
# ast_type_map's kind column is lowercase.
STRUCTURAL_KINDS = {"definition", "flow", "error", "external", "transform", "statement"}
# Filter, combinator and example selectors per language, using only classes the
# audit showed reliable there (card_v1c's are Python's, e.g. .fn in C++ is not).
# Selectors checked on the fixtures where a name exists; the rest are syntax
# illustrations (e.g. no C++ fixture defines main).
OVERRIDES = {
    "rust": {"name": ".fn#main   .call#unwrap   .class#Config", "prefix": '.fn[name^="parse_"]',
             "has": ".fn:has(.call#unwrap)", "nothas": ".fn:not(:has(.loop))",
             "comb": [".class#Config .fn", ".mod > .import", ".import ~ .fn", ".class + .class"],
             "examples": [("every function", ".fn"), ("calls to unwrap", ".call#unwrap"),
                          ("structs and enums whose names end with Error", '.class[name$="Error"]'),
                          ("functions defined in the Config impl", ".class#Config .fn"),
                          ("functions without loops", ".fn:not(:has(.loop))")]},
    "cpp": {"name": "function_definition#main   .call#push_back   .class#Config",
            "prefix": 'function_definition[name^="Parse"]',
            "has": "function_definition:has(.throw)", "nothas": "function_definition:not(:has(.loop))",
            # Classes sit inside namespace bodies, so .mod > .class matches nothing (checked).
            "comb": [".class#Config function_definition", "translation_unit > preproc_include",
                     "preproc_include ~ namespace_definition", "function_definition + function_definition"],
            "examples": [("every function definition", "function_definition"), ("calls to push_back", ".call#push_back"),
                         ("classes whose names end with Error", '.class[name$="Error"]'),
                         ("functions defined inside the Config class", ".class#Config function_definition"),
                         ("functions that never throw", "function_definition:not(:has(.throw))")]},
    "c": {"name": ".fn#main   .call#malloc   .class#config_t", "prefix": '.fn[name^="parse_"]',
          "has": ".fn:has(.call#malloc)", "nothas": ".fn:not(:has(.loop))",
          "comb": [".fn#main .call", ".mod > .fn", "preproc_include ~ .fn", ".fn + .fn"],
          "examples": [("every function", ".fn"), ("calls to malloc", ".call#malloc"),
                       ("structs whose names end with _t", '.class[name$="_t"]'),
                       ("calls made inside main", ".fn#main .call"),
                       ("functions without loops", ".fn:not(:has(.loop))")]},
    "java": {"name": ".fn#main   .call#println   .class#Config", "prefix": '.fn[name^="get"]',
             "has": ".fn:has(.call#println)", "nothas": ".fn:not(:has(.try))",
             "comb": [".class#Config .fn", ".mod > .import", ".import ~ .class", ".fn + .fn"],
             "examples": [("every method", ".fn"), ("calls to println", ".call#println"),
                          ("classes whose names end with Exception", '.class[name$="Exception"]'),
                          ("methods of the Config class", ".class#Config .fn"),
                          ("methods without a try block", ".fn:not(:has(.try))")]},
    "javascript": {"name": ".fn#main   .call#fetch   .class#Config", "prefix": '.fn[name^="handle"]',
                   "has": ".fn:has(.call#fetch)", "nothas": ".fn:not(:has(.try))",
                   "comb": [".class#Config .fn", ".mod > import_statement", "import_statement ~ .fn", ".fn + .fn"],
                   "examples": [("every function", ".fn"), ("calls to fetch", ".call#fetch"),
                                ("classes whose names end with Error", '.class[name$="Error"]'),
                                ("methods of the Config class", ".class#Config .fn"),
                                ("functions without a try block", ".fn:not(:has(.try))")]},
    "go": {"name": ".fn#main   .call#Println", "prefix": '.fn[name^="parse"]',
           "has": ".fn:has(.call#Println)", "nothas": ".fn:not(:has(.loop))",
           "comb": [".fn#main .call", "source_file > function_declaration", ".import ~ .fn", ".fn + .fn"],
           "examples": [("every function", ".fn"), ("calls to Println", ".call#Println"),
                        ("functions whose names start with parse", '.fn[name^="parse"]'),
                        ("calls made inside main", ".fn#main .call"),
                        ("functions without loops", ".fn:not(:has(.loop))")]},
    "bash": {"name": ".fn#main", "prefix": '.fn[name^="install_"]',
             "has": ".fn:has(.loop)", "nothas": ".fn:not(:has(.if))",
             "comb": [".fn#main command", ".mod > .fn", ".var ~ .fn", ".fn + .fn"],
             "examples": [("every function", ".fn"), ("every command", "command"),
                          ("functions whose names start with install", '.fn[name^="install_"]'),
                          ("commands run inside main", ".fn#main command"),
                          ("functions without conditionals", ".fn:not(:has(.if))")]},
    "sql": {"name": "invocation#count", "prefix": 'invocation[name^="json_"]',
            "has": "cte:has(invocation#count)", "nothas": "select_expression:not(:has(subquery))",
            # Each statement is wrapped in a `statement` node, so create_table ~ create_view
            # matches nothing; columns are siblings inside one create_table (checked).
            "comb": ["cte invocation", "create_table > column_definition", "column_definition ~ column_definition",
                     "column_definition + column_definition"],
            "examples": [("every table definition", "create_table"), ("calls to count", "invocation#count"),
                         ("function calls whose names start with json", 'invocation[name^="json_"]'),
                         ("function calls inside a CTE", "cte invocation"),
                         ("selects with no subquery", "select_expression:not(:has(subquery))")]},
}


def override_line(line, ov):
    """Rewrite one filter / combinator line of card_v1c with the language's selectors."""
    s = line.strip()
    combs = {"A B ": 0, "A > B": 1, "A ~ B": 2, "A + B": 3}
    for key, i in combs.items():
        if s.startswith(key):
            desc = {0: "B anywhere inside A", 1: "B is a direct child of A",
                    2: "B is a later sibling of A", 3: "B immediately follows A"}[i]
            return "  %-24s%-29s%s" % (key.strip(), desc, ov["comb"][i])
    if s.startswith("#name"):
        return "  %-24s%-30s%s" % ("#name", "exactly this name:", ov["name"])
    if s.startswith('[name^="x"]'):
        return "  %-24s%-30s%s" % ('[name^="x"]', "name starts with x", ov["prefix"])
    if s.startswith(":has(S)"):
        return "  %-24s%-37s%s" % (":has(S)", "contains a descendant matching S", ov["has"])
    if s.startswith(":not(:has(S))"):
        return "  %-24s%-37s%s" % (":not(:has(S))", "contains no descendant matching S", ov["nothas"])
    return line
CLASS_LINE = re.compile(r"^  (\.[a-z]+)((?:\s+\.[a-z]+)*)\s{2,}(.*)$")
# Classes whose node sets the fixture audit showed to be wrong in a language (see
# train/LANGUAGE_NOTES.md). Dropped from that language's card; Python's card is the
# eval card and is never altered.
UNRELIABLE_ALL = {".arith", ".cmp", ".logic", ".bool", ".comment", ".str"}
UNRELIABLE = {
    "rust": {".if", ".member"},
    "cpp": {".fn", ".if", ".import", ".member"},
    "c": {".if", ".import", ".member"},
    "java": {".if", ".catch", ".member"},
    "javascript": {".import"},
    "go": {".mod"},
    "bash": {".call", ".member"},
    "sql": {".fn", ".if", ".loop", ".jump", ".member", ".import"},
}
TYPE_NAME = re.compile(r"[a-z][a-z0-9_]*")
# Sub-nodes and wrappers that are frequent but aren't what a request names: listing
# them as "node types" would invite selectors that double-count (a declarator inside
# every C++ function, a clause inside every if) or match whole files.
NOT_CARD_TYPES = {
    "expression_statement", "statement", "program", "source_file", "translation_unit", "module",
    "function_declarator", "condition_clause", "system_lib_string", "init_declarator",
    "parameter_declaration", "parameter", "formal_parameter", "variable_declarator",
    "import_specifier", "import_clause", "named_imports", "for_clause", "range_clause",
    "else_clause", "expression_case", "default_case", "all_fields", "match_arm",
    "field_declaration", "local_variable_declaration", "short_var_declaration", "var_spec",
    "declaration", "variable_assignment", "file_redirect", "heredoc_redirect", "package_clause",
    "inc_statement", "group_by", "set_operation",
}


def parse_counts(s):
    """'1192 :: function_item=900, closure_expression=292' -> (1192, [(type, n), ...])"""
    if not s or s.startswith("ERROR"):
        return 0, []
    total, _, rest = s.partition(" :: ")
    pairs = []
    for part in rest.split(", "):
        if "=" in part:
            t, n = part.rsplit("=", 1)
            pairs.append((t, int(n)))
    return int(total), pairs


def language_stats(inv_dir, language):
    classes, types = {}, {}
    for f in sorted(os.listdir(inv_dir)):
        inv = json.load(open(os.path.join(inv_dir, f)))
        if inv.get("language") != language:
            continue
        for alias, val in inv.get("aliases", {}).items():
            total, pairs = parse_counts(val)
            c = classes.setdefault(alias, {"total": 0, "types": {}})
            c["total"] += total
            for t, n in pairs:
                c["types"][t] = c["types"].get(t, 0) + n
        for part in (inv.get("node_types") or "").split(", "):
            m = re.match(r"(.+)\((\d+)\)$", part)
            if m:
                types[m.group(1)] = types.get(m.group(1), 0) + int(m.group(2))
    return classes, types


def build(language, base, inv_dir, type_maps):
    if language == "python":
        return base
    name = DISPLAY[language]
    classes, types = language_stats(inv_dir, language)
    kinds = {r["node_type"]: r["kind"] for r in type_maps.get(language, [])}
    out = []
    ov = OVERRIDES.get(language)
    in_examples = in_py_types = False
    for line in base.splitlines():
        if in_examples or in_py_types:
            if line.startswith("  "):
                continue  # card_v1c's Python examples / Python node-type rows, replaced below
            in_examples = in_py_types = False
        if ov and line.strip() == "EXAMPLES":
            out.append("EXAMPLES")
            for nl, sel in ov["examples"]:
                out.append("  %s%s%s" % (nl, " " * max(2, 44 - len(nl)), sel))
            in_examples = True
            continue
        if ov and line.startswith("  ") and not CLASS_LINE.match(line):
            line = override_line(line, ov)
        if line.startswith("You translate") and "over a Python" in line:
            line = line.replace("over a Python", "over a %s" % name)
        m = CLASS_LINE.match(line)
        if m and not line.lstrip().startswith(("#", "[", ":", "A ")):
            aliases = [m.group(1)] + m.group(2).split()
            drop = UNRELIABLE_ALL | UNRELIABLE.get(language, set())
            if ".fn" in drop:
                drop = drop | {".func", ".method"}
            aliases = [a for a in aliases if a not in drop]
            present = [a for a in aliases if classes.get(a, {}).get("total", 0) > 0 or a in (".func", ".method")]
            if not [a for a in present if a not in (".func", ".method")]:
                continue
            seen = {}
            for a in present:
                for t, n in classes.get(a, {}).get("types", {}).items():
                    if TYPE_NAME.fullmatch(t):  # skip punctuation/keyword tokens such as ?, ::, #include
                        seen[t] = seen.get(t, 0) + n
            top = [t for t, _ in sorted(seen.items(), key=lambda kv: -kv[1])[:4]]
            label = re.sub(r"\s*\(.*\)$", "", m.group(3)).strip()
            head = "  " + " ".join(present)
            line = "%-26s%s" % (head, label + ("  (%s)" % ", ".join(top) if top else ""))
        if line.startswith("PYTHON NODE TYPES"):
            out.append("%s NODE TYPES (exact tree-sitter names, written with no dot, when no class fits)" % name.upper())
            pick = [t for t, _ in sorted(types.items(), key=lambda kv: -kv[1])
                    if kinds.get(t) in STRUCTURAL_KINDS and TYPE_NAME.fullmatch(t) and t not in NOT_CARD_TYPES][:16]
            for i in range(0, len(pick), 5):
                out.append("  " + " ".join(pick[i:i + 5]))
            in_py_types = True
            continue
        if "[params=N]" in line:
            continue
        out.append(line)
    return "\n".join(out) + "\n"


def main(inv_dir, type_maps_path):
    base = open(os.path.join(ROOT, "card_v1c.md")).read()
    type_maps = json.load(open(type_maps_path))
    langs = sorted({json.load(open(os.path.join(inv_dir, f)))["language"] for f in os.listdir(inv_dir)})
    os.makedirs(os.path.join(HERE, "cards"), exist_ok=True)
    for language in langs:
        card = build(language, base, inv_dir, type_maps)
        path = os.path.join(HERE, "cards", "card_%s.md" % language)
        open(path, "w").write(card)
        print("wrote %s (%d lines)" % (os.path.relpath(path, ROOT), card.count("\n")))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
