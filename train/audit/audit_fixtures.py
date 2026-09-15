"""Audit every training fixture: parse language, what each semantic class matches,
the .fn:has(.fn) keyword-token leak, and name/type inventories for drafting."""
import json
import os
import sys

W = "/home/teague/Projects/astcss-eval/trees/train/multilang"
OUT = "/tmp/claude-1000/-home-teague-Projects-Tiiny/a8fcb1a6-70fe-485c-be07-2cbb7fe74e80/scratchpad/inventories"
sys.path.insert(0, W)
import verify as V  # noqa: E402

os.makedirs(OUT, exist_ok=True)
man = json.load(open(os.path.join(W, "train/fixtures/MANIFEST.json")))["fixtures"]
ALIASES = [".fn", ".class", ".call", ".loop", ".if", ".jump", ".try", ".catch", ".throw",
           ".import", ".str", ".comment", ".var", ".member", ".comp", ".mod"]

lines, keys = [], []


def q(key, sql):
    lines.append("SELECT '@@BEGIN %s';" % key)
    lines.append(sql)
    keys.append(key)


for fx in man:
    t = V._table(fx)
    lines.append("CREATE TABLE %s AS SELECT * FROM read_ast('%s');" % (t, V._q(os.path.join(W, V.FIXTURES[fx]))))
    q(fx + "|lang", "SELECT '@@ROWS ' || string_agg(language || '=' || nf || 'f/' || n || 'n', ', ') FROM "
      "(SELECT language, count(DISTINCT file_path) nf, count(*) n FROM %s GROUP BY language);" % t)
    for a in ALIASES:
        q("%s|alias|%s" % (fx, a),
          "SELECT '@@ROWS ' || (SELECT count(*) FROM ast_select_from('{t}', '{a}')) || ' :: ' || "
          "coalesce((SELECT string_agg(type || '=' || n, ', ' ORDER BY n DESC) FROM "
          "(SELECT type, count(*) n FROM ast_select_from('{t}', '{a}') GROUP BY type ORDER BY n DESC LIMIT 6)), '');"
          .format(t=t, a=a))
    q(fx + "|fnhasfn",
      "WITH o AS (SELECT s.file_path, s.node_id, x.descendant_count FROM ast_select_from('{t}', '.fn') s "
      "JOIN {t} x ON x.file_path = s.file_path AND x.node_id = s.node_id), "
      "i AS (SELECT file_path, node_id FROM ast_select_from('{t}', '.fn')), "
      "truth AS (SELECT o.file_path, o.node_id FROM o WHERE EXISTS (SELECT 1 FROM i WHERE i.file_path = o.file_path "
      "AND i.node_id > o.node_id AND i.node_id <= o.node_id + o.descendant_count)) "
      "SELECT '@@ROWS ' || (SELECT count(*) FROM truth) || ' truth / ' || "
      "(SELECT count(*) FROM ast_select_from('{t}', '.fn:has(.fn)')) || ' engine';".format(t=t))
    for kind, alias, limit in (("fn_names", ".fn", 60), ("class_names", ".class", 40), ("call_names", ".call", 60)):
        q("%s|%s" % (fx, kind),
          "SELECT '@@ROWS ' || coalesce(string_agg(name || '(' || n || ')', ', ' ORDER BY n DESC, name), '') FROM "
          "(SELECT name, count(*) n FROM ast_select_from('%s', '%s') WHERE name IS NOT NULL AND name <> '' "
          "GROUP BY name ORDER BY n DESC, name LIMIT %d);" % (t, alias, limit))
    q(fx + "|node_types",
      "SELECT '@@ROWS ' || string_agg(type || '(' || n || ')', ', ' ORDER BY n DESC) FROM "
      "(SELECT type, count(*) n FROM %s WHERE NOT is_syntax_only(flags) GROUP BY type ORDER BY n DESC LIMIT 45);" % t)

got = V._collect(V._run_script(lines), "@@ROWS")
for fx in man:
    inv = {"fixture": fx, "language": man[fx]["language"], "files": len(man[fx]["files"]), "aliases": {}}
    for k in keys:
        if not k.startswith(fx + "|"):
            continue
        g = got.get(k, {})
        val = g.get("payload") if "error" not in g else "ERROR " + g["error"][:160]
        part = k.split("|", 2)
        if part[1] == "alias":
            inv["aliases"][part[2]] = val
        else:
            inv[part[1]] = val
    json.dump(inv, open(os.path.join(OUT, fx + ".json"), "w"), indent=1)
    print("== %s (%s, %d files) parsed as: %s" % (fx, inv["language"], inv["files"], inv.get("lang")))
    print("   .fn:has(.fn): %s" % inv.get("fnhasfn"))
    for a in ALIASES:
        print("   %-9s %s" % (a, (inv["aliases"].get(a) or "")[:120]))
