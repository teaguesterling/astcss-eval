"""Name inventories for the holdout fixtures, read from the engine.

ast_select_from exposes a `name` column, so names come from the engine rather than from
parsing the source by hand. What matters for a validation suite is the COUNT per name: a
reference must land in verify's 1..50, so `.fn#name` is only usable for names defined few
enough times. Real repos are large -- ho-ts-cockpit has 1,270 `.fn` -- which is exactly why
the suite leans on specific questions rather than bare-class ones.
"""
import json, os, subprocess, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import verify as V

FX = sorted(json.load(open(os.path.join(HERE, "holdout/fixtures/MANIFEST.json")))["fixtures"])
lines = ["SET VARIABLE x = 1;"]
if V.MACROS and os.path.exists(V.MACROS):
    lines.append(".read %s" % V.MACROS)
for fx in FX:
    pat = os.path.join(HERE, V.FIXTURES[fx])
    lines.append("CREATE TABLE %s AS SELECT * FROM read_ast('%s');" % (V._table(fx), pat))
    for kind, alias, lim in (("fn", ".fn", 120), ("class", ".class", 80), ("call", ".call", 120)):
        lines.append("SELECT '@@BEGIN %s|%s';" % (fx, kind))
        lines.append(
            "SELECT '@@ROWS ' || coalesce(string_agg(name || '(' || n || ')', ', ' "
            "ORDER BY n, name), '') FROM (SELECT name, count(*) n FROM ast_select_from('%s','%s') "
            "WHERE name IS NOT NULL AND name <> '' GROUP BY name HAVING count(*) <= 40 "
            "ORDER BY n, name LIMIT %d);" % (V._table(fx), alias, lim))
out = V._collect(V._run_script(lines), "@@ROWS")
inv = {}
for k, v in out.items():
    inv[k] = v.get("payload", "") if "error" not in v else ""
json.dump(inv, open(os.path.join(HERE, "workspace/holdout_names.json"), "w"), indent=1)
for fx in FX:
    f = inv.get("%s|fn" % fx, ""); c = inv.get("%s|call" % fx, ""); cl = inv.get("%s|class" % fx, "")
    print("%-22s fn=%-4d class=%-4d call=%-4d" % (fx, f.count("("), cl.count("("), c.count("(")))
    if f: print("      fn e.g. %s" % f[:120])
