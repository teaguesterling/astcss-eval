"""The runtime half of the same rule: bare identifier -> variable, quoted -> literal.

    python3 test_resolve_payload.py

Deliberately exercises the bare-identifier branch FIRST, because that is the path the
change exists to serve and the one most likely to break on a missing import.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "mutator"))
import runtime as R  # noqa: E402

fails = []


def check(label, got, want):
    ok = got == want
    print("  %-4s %-52s got=%r" % ("OK" if ok else "FAIL", label, got))
    if not ok:
        fails.append("%s: got %r want %r" % (label, got, want))


PARAMS = {"new_code": "def f():\n    return 1", "target": ".fn#save"}

print("== bare identifier resolves against params ==")
check("declared variable", R.resolve_payload("new_code", PARAMS), PARAMS["new_code"])
check("declared variable (selector-ish)", R.resolve_payload("target", PARAMS), ".fn#save")

print("\n== undeclared bare identifier passes through, does not raise ==")
check("undeclared", R.resolve_payload("nope", PARAMS), "nope")
check("no params at all", R.resolve_payload("new_code", {}), "new_code")

print("\n== quoted values are literals, not lookups ==")
check("quoted, shadows a param name", R.resolve_payload('"new_code"', PARAMS), "new_code")
check("single-quoted literal", R.resolve_payload("'retries=3'", PARAMS), "retries=3")
check("escape expansion kept", R.resolve_payload(r'"a\nb"', PARAMS), "a\nb")

print("\n== the removed magic is now just text ==")
check("params.new_code is not a prefix any more",
      R.resolve_payload("params.new_code", PARAMS), "params.new_code")
check("${target} is not interpolated",
      R.resolve_payload("${target}", PARAMS), "${target}")

print("\n== fromFile still works ==")
with tempfile.TemporaryDirectory() as td:
    p = os.path.join(td, "auth.py")
    with open(p, "w") as f:
        f.write("SECRET = 1\n")
    check("fromFile reads the file",
          R.resolve_payload('fromFile("auth.py")', PARAMS, base_dir=td), "SECRET = 1\n")
    missing = R.resolve_payload('fromFile("nope.py")', PARAMS, base_dir=td)
    check("missing file reports rather than raises", "not found" in missing, True)

print("\n%d failure(s)" % len(fails))
for f in fails:
    print("   ", f)
sys.exit(1 if fails else 0)
