"""Turn the 65 verified tier-5 candidates into eval pairs by writing their requests.

The gloss a candidate carries ("functions that contain at least one loop and contain no
calls named get") is unambiguous but it is a transliteration of the selector: "contains at
least one X and contains no Y" maps one-to-one onto `:has(X):not(:has(Y))`. An eval built
on glosses measures whether the model can transcribe, not whether it can select.

So each request below is written the way someone would actually ask, and each is checked
against two rules learned the hard way on a separate corpus:

  * ANSWERABLE. Everything the selector encodes must be recoverable from the words. A
    request that omits a constraint the label carries is a free ceiling penalty on every
    model at every skill level.
  * UNAMBIGUOUS. No phrasing that a careful reader could resolve two ways. "between 6am and
    12pm" cost a 4B five points on a sibling corpus for exactly this reason.

Paraphrases exist so the eval is not testing one sentence template. They are a second way of
asking, not a restatement.
"""
import json, os, sys
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

NL = {
".fn:has(.loop):not(:has(.call#get))": ("functions with a loop that never call get", "which routines iterate but never touch get?"),
".mod:has(.loop):not(:has(.import))": ("files that loop somewhere but import nothing", "which modules have iteration and no imports at all?"),
".fn:has(.call#len):has(for_statement)": ("functions that use len and also have a for loop", "which routines call len and iterate with for?"),
"function_definition:not(:has(.call#expensive_computation)):has(.call)": ("function definitions that call something, but never expensive_computation", "routines that make calls while avoiding expensive_computation"),
".fn:has(.call):has(.jump)": ("functions that both call something and return, break or continue", "which routines make a call and also jump out?"),
".fn:not(:has(.call#len)):has(expression_statement)": ("functions with a bare expression statement that never call len", "routines containing a standalone expression and no len call"),
".fn:has(.loop):not(:has(expression_statement))": ("looping functions with no bare expression statements", "which routines iterate without any standalone expression?"),
".fn:not(:has(.member)):has(.jump)": ("functions that return, break or continue but never access an attribute", "routines that jump out and touch no attributes"),
".class:not(:has(.loop)):has(if_statement)": ("classes that branch on an if but contain no loops", "which types have conditionals and no iteration?"),
".class#DatabaseConnection .fn:not(:has(.call#create_connection))": ("methods of DatabaseConnection that never call create_connection", "which DatabaseConnection members avoid create_connection?"),
".class#Config .fn:not(:has(.call#open))": ("methods of Config that never call open", "which Config members avoid open?"),
".class#UserService .fn:is-called": ("methods of UserService that something in the file calls", "which UserService members are actually used?"),
".class#Dog .fn:is-called": ("methods of Dog that something in the file calls", "which Dog members are actually used?"),
".class#Config .fn:not(:is-called)": ("methods of Config that nothing in the file calls", "dead members of Config"),
".class#DatabaseConnection .var:has(.call)": ("variables inside DatabaseConnection whose value comes from a call", "assignments in DatabaseConnection that invoke something"),
".class#Animal .fn:not(:is-called)": ("methods of Animal that nothing in the file calls", "dead members of Animal"),
".fn:calls(get_user):not(:has(.var))": ("functions calling get_user directly and defining no variables", "routines that invoke get_user in their own body and assign nothing"),
".fn:is-called:not(:has(.call#Cat))": ("functions that get called and never construct a Cat", "used routines that avoid Cat"),
".call:called-by(level2)": ("calls made directly in level2's own body", "what does level2 itself invoke?"),
".fn:is-called:has(expression_statement)": ("functions that get called and contain a bare expression statement", "used routines with a standalone expression"),
".fn:is-called:not(:has(.throw))": ("functions that get called and never raise", "used routines that throw nothing"),
".fn:is-called:not(:has(.call#items))": ("functions that get called and never call items", "used routines avoiding items"),
".fn:calls(print):not(:has(.call#create_user))": ("functions printing directly that never call create_user", "routines invoking print in their own body while avoiding create_user"),
".fn:typed:has(.jump)": ("functions with a declared return type that return, break or continue", "annotated routines that jump out"),
".fn:typed:has(.if)": ("functions with a declared return type that branch", "annotated routines containing a conditional"),
".fn:typed:not(:has(expression_statement))": ("functions with a declared return type and no bare expression statements", "annotated routines with no standalone expression"),
".fn:has(return_statement):has(.loop)": ("functions that loop and also have an explicit return statement", "routines that iterate and return"),
".fn:not(:has(.jump)):has(if_statement)": ("functions with an if that never return, break or continue", "branching routines that never jump out"),
".fn:not(:has(with_statement)):has(.comp)": ("functions using a comprehension and no with block", "routines with a comprehension and no context manager"),
".fn:has(.call#capitalize):has(.jump)": ("functions that call capitalize and also return, break or continue", "routines invoking capitalize that jump out"),
".fn:has(.if):not(:has(.call#find_function))": ("functions that branch and never call find_function", "conditional routines avoiding find_function"),
".fn:not(:has(.comp)):not(:has(.call#update_sql_macro))": ("functions with no comprehension that never call update_sql_macro", "routines avoiding both comprehensions and update_sql_macro"),
".fn:not(:has(for_statement)):not(:has(.call#exists))": ("functions with no for loop that never call exists", "routines avoiding for loops and exists"),
".fn:not(:has(.call#group)):not(:has(for_statement))": ("functions that never call group and have no for loop", "routines avoiding group and for iteration"),
".fn:not(:has(.call#escape)):not(:has(.call#to_camel_case))": ("functions that call neither escape nor to_camel_case", "routines avoiding both escape and to_camel_case"),
".fn:not(:has(.call#open)):not(:has(.call#bool))": ("functions that call neither open nor bool", "routines avoiding both open and bool"),
".fn:not(:has(.call#search)):not(:has(.call#generate_def_file))": ("functions that call neither search nor generate_def_file", "routines avoiding both search and generate_def_file"),
".mod:not(:has(.call#classify_node_type)):not(:has(.call#fetchone))": ("files that call neither classify_node_type nor fetchone", "modules avoiding both classify_node_type and fetchone"),
".mod:not(:has(break_statement)):not(:has(.call#capitalize))": ("files with no break statement that never call capitalize", "modules avoiding breaks and capitalize"),
".fn#determine_flags .call[receiver=\"node_name\"]": ("calls on node_name inside determine_flags", "what determine_flags invokes on node_name"),
".fn#replace .call[receiver=\"to_find\"]": ("calls on to_find inside replace", "what replace invokes on to_find"),
".fn:is-called:not(:has(.call#relative_to))": ("functions that get called and never call relative_to", "used routines avoiding relative_to"),
".fn:not(:is-called):has(.member)": ("functions nothing calls that still access an attribute", "dead routines that touch attributes"),
".fn:is-called:not(:has(.loop))": ("functions that get called and never loop", "used routines with no iteration"),
".fn:typed:not(:has(.call#readlines))": ("functions with a declared return type that never call readlines", "annotated routines avoiding readlines"),
".fn:not(:typed):not(:has(with_statement))": ("functions with no declared return type and no with block", "unannotated routines without a context manager"),
".fn:not(:typed):has(.comp)": ("functions with no declared return type that use a comprehension", "unannotated routines containing a comprehension"),
".fn:not(:typed):not(:has(.jump))": ("functions with no declared return type that never return, break or continue", "unannotated routines that never jump out"),
}

# the bare families, written once each rather than transliterated
for recv in ("data", "email", "result", "chunks", "glob", "name_extension",
             "new_name", "entries", "search_parser"):
    NL['.call[receiver="%s"]' % recv] = ("methods invoked on %s" % recv,
                                         "what gets called on %s?" % recv)
for fn in ("escape_raw_string_delimiter", "replace", "update_index", "__init__",
           "get_file_functions", "get_query_result", "replace_everywhere"):
    NL[".call:called-by(%s)" % fn] = ("calls made directly in %s's own body" % fn,
                                      "what does %s itself invoke?" % fn)


def main():
    rows = [json.loads(l) for l in open(os.path.join(HERE, "workspace/t5-b3-verified.jsonl"))]
    out, missing = [], []
    for i, r in enumerate(rows):
        hit = NL.get(r["css"])
        if not hit:
            missing.append(r["css"]); continue
        nl, para = hit
        out.append({"id": "t5-p%03d" % (100 + i), "tier": "5", "nl": nl,
                    "paraphrases": [para], "css": r["css"], "fixture": r["fixture"],
                    "distractors": r["distractors"], "struct": r.get("struct"),
                    "reference": r["reference"], "verification": r["verification"],
                    "gloss": r["gloss"]})
    if missing:
        print("NO REQUEST WRITTEN for %d selectors:" % len(missing))
        for m in missing: print("   ", m)
    dst = os.path.join(HERE, "eval_t5/pairs/accepted-t5-b3.jsonl")
    with open(dst, "w") as fh:
        for r in out:
            fh.write(json.dumps(r) + "\n")
    print("wrote %d pairs -> %s" % (len(out), dst))


if __name__ == "__main__":
    main()
