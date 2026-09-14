# Text-to-ASTCSS — Validation Set & Tinny Harness
*Goal: an execution-verified corpus of (natural language → selector) pairs large enough to validate — and later tune — a small model on the Tinny box. House rule inherited from quay: the engine is the verifier; no pair enters the corpus unless sitting_duck executes it and the node-set matches the blessed reference.*

## 1. Pair schema (JSONL)
```json
{"id":"t4-017","tier":4,"dialect":"astcss","grammar_scope":["python"],
 "nl":"Which functions are missing docstrings?",
 "selector":".fn:not(:has(:docblock))",
 "reference":"sql:docblock_antijoin_v1",
 "paraphrases":["find undocumented functions","functions with no doc block"],
 "distractors":[".fn:not(:docblock)",".fn :not(:has(:docblock))"],
 "fixture":"repo-small-py"}
```
`reference` names a blessed query (selector or raw SQL) whose executed node-id set defines correctness. `distractors` are near-miss selectors that parse but return the wrong set — they exist to catch execution-match, not string-match. A separate optional `refusals` array holds constructs that must *refuse* rather than mismatch — standing members on every pair: `[WHERE …]` (removed from astcss, §2n — models cross-trained on our earlier docs or web SQL/CSS mixtures will hallucinate it) and captures inside `:not`/`:has` (D-N9: negated context has no row to bind). Pairs with captures add `"captures":["f","r"]` naming expected output aliases. Every pair carries ≥2 paraphrases (NL diversity is the training signal; the selector is the invariant).

## 2. Difficulty tiers (coverage matrix: tier × grammar × fixture)
- **T1** bare type/class: "all functions" → `.fn`; "every import" → `.import`
- **T2** attribute ops: "functions named main" → `.fn[name="main"]`; "files under src/auth" → `file[path^="src/auth/"]`; later `?=`/`/=`
- **T3** structure: descendant/child/sibling: "calls inside loops" → `.loop .call`; "the first statement of each function" → `.fn > .block > *:first-child`
- **T4** negation & containment: `:not`, `:has` — the docblock family lives here (note `:docblock` is a registered predicate, not a class — T4 pairs exercise the pseudo-class registry)
- **T5** registered predicates: `:in-glob(...)`, `:callee-of("Y")` — macro-backed pseudo-classes
- **T6** other vocabularies: documents ("every table right after an h2" → `section h2 + table`), http ("POSTs to anything but github" → `request[method="POST"]:not(host[name$="github.com"] *)`), sql-as-28th-grammar with quoted keyword types ("select statements containing subqueries" → `"select":has("select")`)
- **T7** language conversion, per the registry: jQuery `$(...)` chains ↔ astcss; **tsq ↔ astcss** — harvest real `.scm` files (highlights/tags) as source-side inputs, a free real-world distribution; xpath ↔ astcss. Conversions are scored by **TREEQL normal-form equality** (the MN24/P22 machinery *is* the scorer), execution-match as backstop
- **T8 (stretch)** single umwelt rules: NL constraint → `selector { property: value; }` — the on-ramp to text-to-umwelt
- **T9** captures: postfix `@name`, single and multi ("each function and its first return" → `.fn@f > .block .return@r`); pairs carry `captures`; refusal cases: capture under `:not`/`:has`. References freeze *(embedding → alias→node-id map)* sets, not bare node sets

## 3. Seed set (24 pairs, tier-stamped — expand via §5)
```jsonl
{"id":"t1-001","tier":1,"nl":"list every function","selector":".fn"}
{"id":"t1-002","tier":1,"nl":"all class definitions","selector":".class"}
{"id":"t1-003","tier":1,"nl":"every string literal","selector":".string"}
{"id":"t1-004","tier":1,"nl":"show all imports","selector":".import"}
{"id":"t2-001","tier":2,"nl":"functions called main","selector":".fn#main","paraphrase_selector":".fn[name=\"main\"]"}
{"id":"t2-002","tier":2,"nl":"functions whose name starts with test_","selector":".fn[name^=\"test_\"]"}
{"id":"t2-003","tier":2,"nl":"python files in src/auth","selector":"file[path^=\"src/auth/\"][path$=\".py\"]"}
{"id":"t2-004","tier":2,"nl":"identifiers containing password","selector":".identifier[name*=\"password\"]"}
{"id":"t3-001","tier":3,"nl":"function calls inside loops","selector":".loop .call"}
{"id":"t3-002","tier":3,"nl":"classes that directly contain a function named __init__","selector":".class > .fn[name=\"__init__\"]"}
{"id":"t3-003","tier":3,"nl":"the first statement of every function body","selector":".fn > .block > *:first-child"}
{"id":"t3-004","tier":3,"nl":"comments immediately before a function","selector":".comment + .fn"}
{"id":"t4-001","tier":4,"nl":"functions missing docstrings","selector":".fn:not(:has(:docblock))"}
{"id":"t4-002","tier":4,"nl":"try blocks with no except handler","selector":".try:not(:has(.except))"}
{"id":"t4-003","tier":4,"nl":"functions that never call anything","selector":".fn:not(:has(.call))"}
{"id":"t4-004","tier":4,"nl":"classes without a base class","selector":".class:not([bases])"}
{"id":"t5-001","tier":5,"nl":"config files under /etc/ssh","selector":"file:in-glob(\"/etc/ssh/*.conf\")"}
{"id":"t5-002","tier":5,"nl":"functions that y calls directly","selector":".fn:callee-of(\"y\")"}
{"id":"t6-001","tier":6,"dialect":"astcss","grammar_scope":["markdown"],"nl":"every table right after a level-2 heading","selector":"section h2 + table"}
{"id":"t6-002","tier":6,"grammar_scope":["markdown"],"nl":"code blocks inside the Results section","selector":"section:has(h2[content*=\"Results\"]) code"}
{"id":"t6-003","tier":6,"grammar_scope":["http"],"nl":"POST requests to hosts other than github","selector":"request[method=\"POST\"]:not(host[name$=\"github.com\"] *)"}
{"id":"t7-001","tier":7,"dialect":"jq","nl":"functions missing docstrings, jquery style","selector":"$(\".fn\").not(\":has(:docblock)\")","reference":"astcss:t4-001"}
{"id":"t7-002","tier":7,"dialect":"jq","nl":"test functions inside classes","selector":"$(\".class\").find(\".fn[name^=test_]\")","reference":"astcss:t2-002-scoped"}
{"id":"t8-001","tier":8,"dialect":"umwelt","nl":"nobody may modify the authenticate function","selector":"node.fn[name=\"authenticate\"] { modify: deny; }"}
```

## 4. Harness (runs on the Tinny)
1. **Prompting:** fixed system prompt (vocabulary card: the taxonomy classes, operators, registered predicates — i.e., Sheet 1 of the cheatsheets, machine-trimmed) + NL → selector. **Four arms, 2×2 (language × constraint):** (A) astcss free, (B) astcss **GBNF-constrained** — the grammar is now *closed with no carve-outs* (no host escape, §2n), which is exactly what constrained decoding wants; (C) **TREEQL free** — the no-phrasebook regime: a grammar so SQL-shaped the base model barely needs the card; (D) TREEQL GBNF. A–B tests the constrained-decoding thesis; A–C tests phrasebook-vs-SQL-shape; C–D should show the smallest gap — if it doesn't, the TREEQL grammar sketch is wrong somewhere.
2. **Scoring, in order of authority:** parse-valid % → **execution-match %** (node-id or capture-map equality vs reference on the fixture repos) → **normal-form-match %** (compile to TREEQL normal form; equality there catches semantically-identical spellings across and within languages) → exact-string % (tertiary; canonicalize via `idiom` — which prefers `#x` over `[<id-attr>="x"]` under the shape's ID binding; the two are execution-equal but NF-distinct, an *expected* divergence, not a corpus bug). Refusal cases score pass iff refused with the routing hint. Report per tier × grammar; latency and tok/s per arm.
3. **Fixtures:** three pinned corpora (`repo-small-py` ~30 files; `repo-polyglot` py+rust+js; `docs-set` markdown+html), content-hashed, with a parse manifest — results cite the manifest, per house doctrine.
4a. **Dependency:** the vocabulary card derives from cheatsheet Sheet 1, which is flagged stale in the inventory — refresh (ROWS, `:docblock`, `@captures`, quoted types, no `[WHERE]`) before any harness run; a stale card invalidates arm A/B comparisons.
4b. **Distractor audit:** every distractor must (a) parse and (b) fail execution-match; a distractor that accidentally matches the reference is a bug in the pair, caught in CI.

## 5. Generator sub-agent (master prompt, condensed)
> You generate (NL, selector) pairs for the Text-to-ASTCSS corpus. You have `ast_select` execution access against the pinned fixtures. Loop: (1) pick an under-filled cell of the tier×grammar coverage matrix; (2) write a selector that is *true of the fixture* (returns 1–50 nodes — never 0, never the universe); (3) execute it and freeze the node-id set as reference; (4) write one plain NL description a developer would actually type, then 2–4 paraphrases at different registers (terse, verbose, imperative, question); (5) write 2 near-miss distractors and verify each parses and mismatches; (6) emit JSONL. Hard rules: never emit `[WHERE …]` — astcss has no host escape (it appears in superseded docs; treat any urge to use it as a signal to mint a `refusals` entry instead); captures only per T9 and never inside `:not`/`:has`; **every pair T3 and above ships its TREEQL twin** (mechanical translation — each twin is a free P22/MN24 conformance fixture, and arm-C/D training data); never emit a pair you did not execute; NL must not mention selector syntax; paraphrases must not share more than half their content words; reject any selector `idiom` rewrites to an existing pair's canonical form (dedup by canonicalized selector + node-set hash). Target: 400 pairs/tier for T1–T4, 150 for T5–T7, 50 for T8. File a FINDINGS note for every taxonomy gap you hit — a concept you could not express is corpus gold.

*Scale note: seed (24) → generator (~2,500) → TREEQL twins (×2 on T3+) → paraphrase augmentation (×3–4 NL variants) ≈ 15–18k training rows with ~2,500 unique execution-verified semantics, plus the harvested `.scm` conversion set riding on top. The verifier makes the corpus cheap; the taxonomy gaps it surfaces feed Paper 3's leaks matrix for free.*
