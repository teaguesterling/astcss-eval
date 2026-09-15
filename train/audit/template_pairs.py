"""C++ template pairs (2026-09-15, sitting_duck #158/#159): selecting templated code.

Two batches from the three C++ fixtures:

  templates-c1   engine-verified today: template_declaration, template_declaration > .fn,
                 .class template_declaration, .class:has(template_declaration) ...
                 -> train/candidates/templates-c1.jsonl, verified with pilot.py like any training batch.
  templated-c1   the proposed :templated pseudo-class (#159), written against documented semantics
                 (oracle.py) with calls named after their template (#158's fix), verified with
                 oracle.verify_batch into train/later/ -- pending until the engine has :templated,
                 and kept out of train/pairs so no dataset picks them up yet.

    python3 train/audit/template_pairs.py write        # candidates only
    python3 train/audit/template_pairs.py later        # verify templated-c1 into train/later
    python3 pilot.py train/candidates/templates-c1.jsonl templates-c1 train --paraphrases=distinct

When #159 lands, the templates-c1 requests that say "templated" should move to the :templated
selectors; the two batches share wording on purpose so that switch is a lookup.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, HERE)
import audit_pairs  # noqa: E402
import oracle as O  # noqa: E402
import pilot  # noqa: E402

MCP, YAML, HUNT = "cpp-duckdb-mcp", "cpp-duckdb-yaml", "cpp-duck-hunt"

# (id, fixture, css, [nl, paraphrase, paraphrase], [distractors])
VERIFIED = [
    ("tr-cpp-t1-y0001", MCP, "template_declaration",
     ["template declarations in the mcp code", "where does the mcp extension declare a template?", "find every template declaration in the connection layer"],
     ["function_definition", "template_parameter_list"]),
    ("tr-cpp-t1-y0002", YAML, "template_declaration",
     ["template declarations in the yaml extension", "where does the yaml code declare a template?", "find every template declaration in the reader"],
     ["function_definition", "template_parameter_list"]),
    ("tr-cpp-t1-y0003", HUNT, "template_declaration",
     ["template declarations in duck hunt", "where does duck hunt declare a template?", "find every template declaration in the parsers"],
     ["alias_declaration", "template_parameter_list"]),
    ("tr-cpp-t3-y0004", MCP, "template_declaration > .fn",
     ["function templates in the mcp code", "which functions are declared as templates?", "find function definitions written as templates"],
     [".fn", "template_declaration .call"]),
    ("tr-cpp-t3-y0005", YAML, "template_declaration > .fn",
     ["function templates in the yaml extension", "which yaml functions are declared as templates?", "find templated function definitions"],
     [".fn", "template_declaration .call"]),
    ("tr-cpp-t3-y0006", YAML, "template_declaration > .fn#MakeLimitGetter",
     ["the MakeLimitGetter function template", "where is MakeLimitGetter defined as a template?", "find the MakeLimitGetter template definition"],
     [".fn#MakeLimitGetter", "template_declaration > .fn#MakeLimitSetter"]),
    ("tr-cpp-t3-y0007", MCP, ".class template_declaration",
     ["template declarations inside a class", "which templates are declared as class members?", "find member template declarations"],
     ["template_declaration", ".class .fn"]),
    ("tr-cpp-t4-y0009", MCP, ".class:has(template_declaration)",
     ["classes that declare a member template", "which classes contain a template method?", "find classes with a template declaration inside"],
     [".class:not(:has(template_declaration))", ".class:has(.fn)"]),
]

# :templated (#159) -- (id, fixture, css, texts, distractors)
LATER = [
    ("tr-cpp-t5-z0001", MCP, ".fn:templated",
     ["templated functions in the mcp code", "which functions are declared as templates?", "function templates in the connection layer"],
     [".fn", ".fn:not(:templated)"]),
    ("tr-cpp-t5-z0002", YAML, ".fn:templated",
     ["templated functions in the yaml extension", "which yaml functions are templates?", "function templates in the reader"],
     [".fn", ".class .fn"]),
    ("tr-cpp-t5-z0003", MCP, ".class .fn:templated",
     ["template methods declared inside a class", "which class member functions are templates?", "templated member functions"],
     [".class .fn", ".fn:templated"]),
    ("tr-cpp-t5-z0004", MCP, ".class#MCPLogger .fn:not(:templated)",
     ["methods of MCPLogger that are not templates", "which MCPLogger functions are ordinary non-template methods?", "MCPLogger member functions without a template declaration"],
     [".class#MCPLogger .fn", ".class#MCPLogger .fn:templated"]),
    ("tr-cpp-t5-z0005", MCP, ".fn#ValueToJSON .call:templated",
     ["templated calls inside ValueToJSON", "which calls in ValueToJSON pass explicit template arguments?", "calls with a template argument list within ValueToJSON"],
     [".fn#ValueToJSON .call", ".fn#ValueToJSON .call:not(:templated)"]),
    ("tr-cpp-t5-z0006", MCP, ".fn#Read .call:not(:templated)",
     ["calls in Read without template arguments", "which Read calls are plain, not templated?", "ordinary calls inside Read with no template argument list"],
     [".fn#Read .call", ".fn#Read .call:templated"]),
    ("tr-cpp-t5-z0007", MCP, ".call#GetValue:templated",
     ["templated GetValue calls", "which GetValue calls spell out a template type argument?", "GetValue invocations with explicit template arguments"],
     [".call#GetValue", ".call#GetValue:not(:templated)"]),
    ("tr-cpp-t5-z0008", MCP, ".fn#Read .call:templated",
     ["templated calls inside Read", "which calls in Read pass explicit template arguments?", "calls with a template argument list within Read"],
     [".fn#Read .call", ".call:templated"]),
    ("tr-cpp-t5-z0009", YAML, ".fn#CopyToYAMLPlan .call:templated",
     ["templated calls inside CopyToYAMLPlan", "which calls in CopyToYAMLPlan pass explicit template arguments?", "calls with a template argument list within CopyToYAMLPlan"],
     [".fn#CopyToYAMLPlan .call", ".fn#CopyToYAMLPlan .call:not(:templated)"]),
    ("tr-cpp-t5-z0010", YAML, ".fn#RegisterLimitFunctions .call:templated",
     ["templated calls inside RegisterLimitFunctions", "which calls in RegisterLimitFunctions pass template arguments?", "calls with a template argument list within RegisterLimitFunctions"],
     [".fn#RegisterLimitFunctions .call", ".call:templated"]),
    ("tr-cpp-t5-z0012", HUNT, ".fn#RegisterInfrastructureParsers .call:templated",
     ["templated calls inside RegisterInfrastructureParsers", "which calls in RegisterInfrastructureParsers pass template arguments?", "calls with a template argument list within RegisterInfrastructureParsers"],
     [".fn#RegisterInfrastructureParsers .call", ".call:templated"]),
    ("tr-cpp-t5-z0013", HUNT, ".fn#CalculateMessageSimilarity .call:templated",
     ["templated calls inside CalculateMessageSimilarity", "which calls in CalculateMessageSimilarity pass template arguments?", "calls with a template argument list within CalculateMessageSimilarity"],
     [".fn#CalculateMessageSimilarity .call", ".fn#CalculateMessageSimilarity .call:not(:templated)"]),
]


def check_texts(css, fixture, texts):
    probs = []
    for t in texts:
        if pilot.SELECTOR_SYNTAX.search(t):
            probs.append("selector syntax: %r" % t)
        probs += ["%r: %s" % (t, w) for w in audit_pairs.request_reasons(css, t, fixture)]
    return probs


def write():
    rows, probs = [], []
    for pid, fx, css, texts, dis in VERIFIED:
        probs += ["%s %s" % (pid, p) for p in check_texts(css, fx, texts)]
        rows.append({"id": pid, "tier": O.tier(O.parse(css)), "fixture": fx, "nl": texts[0], "paraphrases": texts[1:],
                     "css": css, "distractors": dis, "treeql": None})
    for pid, fx, css, texts, dis in LATER:
        probs += ["%s %s" % (pid, p) for p in check_texts(css, fx, texts)]
        if O.parse(css) is None:
            probs.append("%s: oracle can't parse %s" % (pid, css))
    if probs:
        sys.exit("problems:\n  " + "\n  ".join(probs))
    path = os.path.join(HERE, "train", "candidates", "templates-c1.jsonl")
    with open(path, "w") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("wrote %s (%d candidates); %d :templated candidates checked" % (os.path.relpath(path, HERE), len(rows), len(LATER)))


def later():
    O.DOCUMENTED_TEMPLATE_CALL_NAMES = True
    rows = []
    for pid, fx, css, texts, dis in LATER:
        rows.append({"id": pid, "fixture": fx, "nl": texts[0], "paraphrases": texts[1:], "struct": O.parse(css),
                     "distractor_structs": [O.parse(d) for d in dis]})
    out, meta = O.verify_batch(rows, "templated-c1", os.path.join(HERE, "train", "later"), "distinct")
    print(json.dumps({k: meta[k] for k in ("accepted", "pending", "rejected", "tier_verdicts")}))
    for r in out["rejected"]:
        print("  rejected %s %s: %s" % (r["id"], r["css"], "; ".join(r["reasons"])[:220]))
    for r in out["pending"] + out["accepted"]:
        print("  %s %-48s %2d nodes %s" % (r["id"], r["css"], r["reference"]["count"], r["tags"]))


if __name__ == "__main__":
    {"write": write, "later": later}[sys.argv[1]]()
