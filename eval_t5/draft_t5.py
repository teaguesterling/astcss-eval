"""Tier-5 held-out eval pairs: hand-written wordings over generated and hand-picked selectors.

Tier 5 is relational and compound selection: several constraints on one node, receivers,
the call graph (:calls, :called-by, :is-called), references and exports, :scope(selector),
modifiers and annotations. It lives beside the original eval, not inside it: qualify.py
loads pairs/accepted-*.jsonl, and the 108-pair numbers must stay comparable.

Selectors come from `tune/gen_pairs.py enumerate --families chain,scoped,receiver,graph,
refs,scope,mods` on the two eval fixtures (eval_t5/candidates/selectors.jsonl), keeping the
ones a developer would plausibly ask for, plus hand-picked selectors for families the
generator rarely produced. Wordings follow the eval's strict rule (no two of request and
paraphrases share more than half their content words). Node sets are the documented
semantics (oracle.py); pairs whose feature the engine gets wrong land in pending with a
pending_engine:<issue> tag until sitting_duck is patched.

usage: python3 eval_t5/draft_t5.py            check wording and gates, no engine
       python3 eval_t5/draft_t5.py --verify   write eval_t5/pairs/*-t5-b1.jsonl
"""
import glob
import json
import os
import random
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tune"))
import oracle as O  # noqa: E402
import pilot  # noqa: E402
import gen_pairs as G  # noqa: E402

ROOT = os.path.join(HERE, "eval_t5")
BATCH = "t5-b1"

# (candidate id | (fixture, selector)), request, [paraphrase, paraphrase], extra distractors
ENTRIES = [
    ("t5c-000008", "functions calling range without any try block",
     ["which routines invoke range but never wrap code in try?", "defs using range that lack exception guarding"], []),
    ("t5c-000012", "functions that call fetch_all and contain no conditionals",
     ["which routines invoke fetch_all without a single if?", "defs using fetch_all where no branching on a condition appears"], []),
    ("t5c-000011", "functions containing both a loop and a conditional",
     ["which routines iterate and also branch on some condition?", "defs that have a for or while plus an if somewhere inside"], []),
    ("t5c-000003", "functions with a loop but no calls at all",
     ["which routines iterate without invoking anything?", "defs looping over data that never call another function"], []),
    ("t5c-010003", "functions using a with block but no except handler",
     ["which routines open a context manager without catching exceptions?", "defs containing with statements where nothing handles errors"], []),
    ("t5c-010008", "functions that catch exceptions but have no if statement",
     ["which routines include an except clause yet never branch with if?", "defs handling errors without any if checks"], []),
    ("t5c-000021", "methods in DatabaseConnection that never call execute",
     ["which DatabaseConnection functions avoid invoking execute?", "defs belonging to DatabaseConnection with no execute invocation"], []),
    ("t5c-000022", "calls on self inside the UserService class",
     ["which self method invocations happen within UserService?", "UserService lines invoking something on self"], []),
    ("t5c-000027", "UserService methods that are never called in the file",
     ["which functions of UserService does nothing invoke?", "unused defs inside UserService"], []),
    ("t5c-000017", "every call made on self inside create_user",
     ["which self methods does create_user invoke?", "method invocations on the self object within the create_user function"], []),
    ("t5c-010016", "calls made on to_find inside replace_everywhere",
     ["which to_find methods get invoked by replace_everywhere?",
      "method invocations whose object is to_find within the replace_everywhere function"], []),
    ("t5c-000026", "functions nested in level3 that contain a level6 call somewhere",
     ["which inner defs of level3 have a call to level6 anywhere inside?", "helpers defined within level3 whose bodies reach a level6 invocation"], []),
    ("t5c-000016", "Animal methods that are called somewhere in their file",
     ["which functions of the Animal class get invoked?", "used defs inside Animal"], []),
    ("t5c-000028", "method calls on animal",
     ["where does the code invoke something on the animal variable?", "invocations whose object is animal"], []),
    ("t5c-000035", "functions that call something on the json module",
     ["which routines use json methods?", "defs containing a json method invocation"], []),
    ("t5c-010018", "calls on the subprocess module",
     ["where is subprocess invoked?", "subprocess method invocations"], []),
    ("t5c-000033", "try blocks that call a method on self",
     ["which exception guarded sections invoke self methods?", "try statements containing a self invocation"], []),
    ("t5c-010020", "functions calling something on the time module",
     ["which routines use time methods?", "defs invoking a method of time"], []),
    ("t5c-000036", "classes whose code calls into the json module",
     ["which class definitions use json methods?", "types containing a json invocation"], []),
    ("t5c-000042", "functions that get called elsewhere in the file and call execute",
     ["which invoked routines themselves run execute?", "used defs containing an execute call"], []),
    ("t5c-000041", "functions that are called somewhere but call nothing themselves",
     ["which invoked routines make no calls of their own?", "leaf defs that something in the file uses"], []),
    ("t5c-000049", "calls made directly inside transform",
     ["which invocations sit in the body of transform?", "every call site within the transform routine"], []),
    ("t5c-010034", "calls made directly in update_file",
     ["what does the update_file function invoke in its own body?", "invocations whose nearest enclosing def is update_file"], []),
    ("t5c-000048", "functions nobody calls that contain a call to get",
     ["which unused routines invoke get?", "defs never invoked in their file whose body uses the get method"], []),
    ("t5c-000047", "functions that are called somewhere and contain a loop",
     ["which invoked routines iterate?", "used defs that loop over something"], []),
    (("py-variety", ".fn:calls(execute)"), "functions whose own body calls execute",
     ["which routines invoke execute directly, not through a nested helper?", "defs making an execute call themselves"],
     [".fn:not(:calls(execute))"]),
    (("py-variety", ".fn:calls(get_user)"), "functions that call get_user directly",
     ["which routines invoke get_user in their own body?", "defs where get_user is called, not counting nested functions"],
     [".fn:calls(execute)"]),
    ("t5c-010043", "public module level functions that something in their file calls",
     ["which top level routines get invoked elsewhere?", "exported defs that have callers"], []),
    (("py-variety", ".fn:async"), "async functions",
     ["which routines are declared asynchronous?", "coroutine defs"], []),
    (("py-variety", '.fn[annotation*="property"]'), "functions decorated with property",
     ["which defs carry the property decorator?", "routines turned into properties"], ['.fn[annotation*="classmethod"]']),
    (("py-variety", '.fn[annotation*="classmethod"]'), "functions decorated as class methods",
     ["which defs carry the classmethod decorator?", "routines marked with classmethod"], ['.fn[annotation*="property"]']),
    (("py-variety", ".fn:calls(print):not(:has(.try))"), "functions that print directly and have no try block",
     ["which routines call print in their own body without a try statement?", "defs printing output with nothing wrapped in try"], []),
    (("py-variety", '.fn[signature="str"]'), "functions whose return type is str",
     ["which routines are annotated to return a string?", "defs declaring an arrow str result"], ['.fn[signature="None"]']),
    (("py-variety", '.call#execute[receiver="self"]'), "calls to the execute method on self",
     ["where does a method invoke its own execute?", "spots where execute is invoked via self"], []),
    ("t5c-010029", "functions that are called somewhere and contain a for statement",
     ["which invoked routines run a for loop?", "used defs iterating with for"], []),
    ("t5c-000013", "functions with an if statement but no with block",
     ["which routines branch on a condition without using a context manager?", "defs containing if checks yet no with statements"], []),
    (("repo-small-py", '.fn:has(.call#run[receiver="subprocess"])'), "functions that start a process with the subprocess run call",
     ["which routines invoke run on subprocess?", "defs launching an external command via subprocess run"], []),
    (("repo-small-py", '.fn[signature="None"]'), "functions annotated to return None",
     ["which routines declare a None return type?", "defs with an arrow None signature"], ['.fn[signature="str"]']),
    (("repo-small-py", ".fn:exported:not(:is-referenced)"), "public module level functions that nothing references",
     ["which exported routines are never used in their file?", "top level public defs with no references to them"], []),
    ("t5c-000053", "public module level functions that are never called in their file",
     ["which top level routines does nothing invoke?", "exported defs with no callers"], []),
    ("t5c-000052", "classes that are referenced somewhere in their file",
     ["which class definitions get used?", "types mentioned elsewhere in the code"], []),
    ("t5c-000061", "methods defined directly in the Cat class",
     ["which functions belong to Cat itself?", "defs whose nearest enclosing class is Cat"], []),
    ("t5c-000059", "calls made in the body of load",
     ["what does the load function invoke directly?", "invocations whose nearest enclosing def is load"], []),
    ("t5c-010047", "variables and parameters defined directly in create_index",
     ["which names does the create_index function bind, arguments included?",
      "assignments and params whose nearest enclosing def is create_index"], []),
    ("t5c-000066", "functions with a declared return type",
     ["which routines have an arrow return annotation?", "typed defs that state what they return"], []),
    ("t5c-010052", "functions without a return type annotation",
     ["which routines declare no result type?", "untyped defs lacking an arrow"], []),
    ("t5c-000068", "functions with a return type and no if statement",
     ["which annotated routines never branch with if?", "typed defs free of if checks"], []),
]


def build_rows():
    cands = {c["id"]: c for c in map(json.loads, open(os.path.join(ROOT, "candidates", "selectors.jsonl")))}
    shapes, taken, eval_css = G.taken_node_sets()
    trees, rows, problems = {}, [], []
    for i, (src, nl, paras, extra) in enumerate(ENTRIES, 1):
        if isinstance(src, str):
            c = cands[src]
            fx, struct = c["fixture"], c["struct"]
            dis = list(c["distractor_structs"])
        else:
            fx, css = src
            struct = O.parse(css)
            if struct is None or O.render(struct) != css:
                problems.append("%s does not parse/round-trip" % css)
                continue
            dis = []
        t = trees.setdefault(fx, O.Tree(fx))
        ref = t.select(struct)
        for e in extra:
            d = O.parse(e)
            if d is None:
                problems.append("distractor %s does not parse" % e)
            elif t.select(d) != ref and O.render(d) not in [O.render(x) for x in dis]:
                dis.insert(0, d)
        if len(dis) < 2:
            en = G.Enumerator(t, "python", random.Random("t5:%d" % i), shapes, taken, eval_css)
            for d in en.distractors(struct, ref):
                if O.render(d) not in [O.render(x) for x in dis]:
                    dis.append(d)
        rows.append({"id": "t5-p%02d" % i, "fixture": fx, "nl": nl, "paraphrases": paras, "struct": struct,
                     "distractor_structs": dis[:2], "tags": ["tier5"], "source": src if isinstance(src, str) else "hand"})
    return rows, trees, problems


def main():
    rows, trees, problems = build_rows()
    for r in rows:
        t = trees[r["fixture"]]
        ref = t.select(r["struct"])
        why = pilot.static_reasons(dict(r, distractors=[O.render(d) for d in r["distractor_structs"]]), "strict")
        why += O.gate_reasons(t, r["struct"], ref, r["distractor_structs"])
        mark = "ok  " if not why else "FIX "
        print("%s %s %-58s n=%-2d %s" % (mark, r["id"], O.render(r["struct"])[:58], len(ref), sorted(O.features(r["struct"]))))
        for w in why:
            print("       - %s" % w)
    for p in problems:
        print("PROBLEM", p)
    if "--verify" in sys.argv:
        taken = {}
        for f in glob.glob(os.path.join(HERE, "pairs", "*.jsonl")):
            if not os.path.basename(f).startswith("rejected-"):
                for line in open(f):
                    p = json.loads(line)
                    if p.get("reference"):
                        taken[(p["fixture"], p["reference"]["sha256"])] = p["id"]
        out, meta = O.verify_batch(rows, BATCH, ROOT, "strict", check_eval_overlap=False, taken=taken)
        print(json.dumps({k: v for k, v in meta.items() if k != "engine"}, indent=1))
        for name in ("pending", "rejected"):
            for r in out[name]:
                print(name, r["id"], r["css"], r.get("tags"), r.get("reasons", "")[:3] if r.get("reasons") else "")


if __name__ == "__main__":
    main()
