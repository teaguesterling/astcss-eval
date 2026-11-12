"""Bare identifiers are variables, quoted strings are literals, and the pairing is
checkable without executing anything.

    python3 test_judge_variables.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "mutator"))
import judge as J  # noqa: E402

fails = []


def check(label, cond, detail=""):
    print("  %-4s %s%s" % ("OK" if cond else "FAIL", label,
                           "" if cond else "   <- " + str(detail)))
    if not cond:
        fails.append(label)


print("== a bare selector parses, a quoted one still does ==")
g = J.parse("$(target).wrapInTry()")
check("bare selector parses", g is not None, g)
check("bare selector is a variable", g and g["selector_kind"] == "variable", g)
check("bare selector name kept", g and g["selector"] == "target", g)

g = J.parse("$('.fn#save').wrapInTry()")
check("quoted selector still parses", g is not None, g)
check("quoted selector is a literal", g and g["selector_kind"] == "literal", g)

print("\n== arguments: bare is a variable, quoted is a literal ==")
g = J.parse("$('.fn#calc').replaceWith(new_code)")
check("bare arg -> variable", g and g["arg_kinds"] == ["variable"], g)
check("variable collected", g and g["variables"] == {"new_code"}, g)

g = J.parse('$(\'.call#c\').addArg("retries=3")')
check("quoted arg -> literal", g and g["arg_kinds"] == ["literal"], g)
check("no variables collected", g and g["variables"] == set(), g)

print("\n== a literal is not the same answer as a variable ==")
task = {"call": "$('.fn#calc').replaceWith(new_code)"}
same = J.score(task, J.parse("$('.fn#calc').replaceWith(new_code)"))
inlined = J.score(task, J.parse("$('.fn#calc').replaceWith(\"new_code\")"))
check("matching variable scores", same["all"] is True, same)
check("inlined literal does NOT score", inlined["args"] is False, inlined)

print("\n== declared vs used, checked statically ==")
check("Variables: line parsed",
      J.declared_in("replace the body of calc. Variables: new_code") == ["new_code"],
      J.declared_in("replace the body of calc. Variables: new_code"))
check("multi-name line parsed",
      J.declared_in("do a thing. Variables: a, b c") == ["a", "b", "c"],
      J.declared_in("do a thing. Variables: a, b c"))
check("absent line -> []", J.declared_in("just do it") == [])

ok, probs = J.check_variables(J.parse("$('.fn#c').replaceWith(new_code)"), ["new_code"])
check("declared and used -> ok", ok, probs)

ok, probs = J.check_variables(J.parse("$('.fn#c').replaceWith(new_code)"), [])
check("undeclared -> flagged", (not ok) and "undeclared" in probs[0], probs)

ok, probs = J.check_variables(J.parse('$(\'.fn#c\').addArg("x")'), ["new_code"])
check("declared but unused -> flagged", (not ok) and "unused" in probs[0], probs)

ok, probs = J.check_variables(J.parse("$(target).wrapInTry()"), ["target"])
check("selector variable counts as used", ok, probs)

print("\n== the old grammar is now simply wrong, not silently accepted ==")
g = J.parse('$("${target}").replaceWith(params.new_code)')
check("${target} selector no longer a bare variable",
      g is None or g["selector_kind"] == "literal", g)
if g:
    check("params.new_code is not a bare identifier",
          g["arg_kinds"] == ["literal"], g)

print("\n== regression: existing well-formed calls still parse and score ==")
t = {"call": '$(\'.fn#search_users\').addComment("WARNING: SQL injection")'}
g = J.parse('$(\'.fn#search_users\').addComment("WARNING: SQL injection")')
s = J.score(t, g)
check("unchanged literal call still scores all", s["all"] is True, s)
st, _ = J.judge('$(\'.fn#save\').wrapInTry().on("KeyError", "return None")')
check("clauses still judged ok", st == "ok", st)

print("\n%d failure(s)" % len(fails))
sys.exit(1 if fails else 0)
