# Findings while building the pilot set

SPEC.md §5 asks for a FINDINGS note for every taxonomy gap or engine defect hit
while generating pairs. Each entry below was checked against the engine the
verifier runs (`verify.engine_identity()`: sitting_duck HEAD build plus the
PR #129 selector macros), on the `py-variety` fixture unless stated.

## Filed upstream (sitting_duck)

| issue | defect | pairs affected here |
|---|---|---|
| #127 / PR #129 | combinator steps ignored `.class` aliases and `#name`; child combinator joined parents across files | fixed in the verifier's macros; no pair depends on the unfixed behaviour |
| #128, #130 | unknown or malformed selector parts are silently ignored | the load-bearing gate exists because of these |
| #131 | Python operator types assigned by token text: decorator `@` is `.arith`, for-loop `in` is `.cmp`, each operation matches twice | t1-p11, t1-p12, t1-p13, t3-p14 held |
| #132 | `is_boolean_literal()` tests `LITERAL_BOOLEAN`, which doesn't exist; `is_semantic_type` accepts unknown names silently; `.bool` includes `None` | t1-p10 held |
| #133 | inside `:has` / `:not(:has)` an alias also matches syntax-only keyword tokens (`def`, `class`, `for`, `as`) | t4-p26 held |
| #134 | `.comment` is kind-level `METADATA` (decorators, `as`) and undocumented | t3-p07 held |
| #139 | classes match sub-nodes of their construct (C++ `.fn` adds `function_declarator`, `.import` adds `system_lib_string` / `import_clause`, Java `.catch` adds `catch_type`, Go `.mod` adds `package_clause`); Bash `.call` misses `command`, Python `.self` is empty | training pairs use node types instead (`train/LANGUAGE_NOTES.md`) |
| #140 | names don't bind: Bash `command`, Go `struct_type` / `interface_type` (name is on `type_spec`), Java imports (name is the whole statement) | training pairs avoid `#name` on these |
| #141 | `A + B` counts punctuation as siblings, so comma-separated siblings are never adjacent (`identifier + identifier` 0 vs `~` 113) | no `+` pairs between list elements |
| #145 | `:scope(selector)` is ignored: `.fn:scope(.class#UserService)` returns every function, `.call:scope(.class#UserService)` none; only a type argument works | tier-5 pairs use the documented meaning, verified by the reference checker (`pending_engine:scope-selector`) |
| #146 | `:calls(name)` is plain containment, not scope-aware as documented: an outer function matches a call inside its nested function | same, `pending_engine:calls-scope` where the two differ |
| #147 | `:is-referenced` matches every named definition (181 of 183 functions on py-blq), so `:not(:is-referenced)` finds no dead code | same, `pending_engine:is-referenced` |
| #148 | `:exported` includes methods and nested functions; documented as module-level public definitions | same, `pending_engine:exported` |
| #149 | `[receiver=X]` collapses chained receivers to the last segment: `self.db.execute()` has receiver `db` | pairs use single-segment receivers where the two meanings agree |
| #150 | the tutorial's capstone selector errors: attribute filters inside `:has` are refused | tier-5 pairs may use them under `pending_engine:attr-in-has` |
| #128 (comment) | captures (`.fn@f`) and unknown class aliases (`.nosuchclass`, `.with_statement`) return 0 without error | captures stay out of pairs |
| #152 | `semantic_type = 'DEFINITION_FUNCTION'` is false for lambdas (code 241 renders as DEFINITION_FUNCTION, 240 is the literal), so `:called-by`'s nearest-function check looks through lambdas. Same for calls (comment): Rust `macro_invocation` (211) and JS `new_expression` (210) are not `= 'COMPUTATION_CALL'`, so `::callees` drops them (`.fn#test_glob_pattern_exact::callees` 0 vs 3) and `::callers` / `:calls` / `:is-called` can miss them | `pending_engine:called-by-lambda`, `pending_engine:call-code-literal` (6 of 35 generated `::callees` differ, all refined-code calls; all 25 `::callers` agree) |
| #158 | C++ `template_function` / `template_method` are mapped to `DEFINITION_FUNCTION` with `NAME_DEFINITION \| IS_SCOPE`, but all 158 in the three C++ fixtures are use sites (112 under `call_expression`, 30 `field_expression`, 16 `qualified_identifier`, 0 in declarators): `.fn` matches `static_cast<int>(x)`, and a call through an explicit template argument list has no name (`.call#twice` 0 for `twice<int>(2)`) | 5 prefix-c1 C++ pairs dropped in the review (`.fn[name^="static"]`, `^="make"`, `$="cast"`, `^="Make"`, `$="Cast"`) |
| #159 (feature) | `:templated` pseudo-class: `.fn:templated`, `.fn:not(:templated)` (no selector can exclude templated definitions today; `template_declaration > .fn` selects them), `.call:templated` for `make_uniq<T>(...)`; depends on #158 | templates-c1: 7 engine-verified `template_declaration` pairs in training; templated-c1: 12 `:templated` pairs (`.fn:templated`, `.class#MCPLogger .fn:not(:templated)`, `.call#GetValue:templated` ...) verified against documented semantics and held pending in `train/later/` |
| #160 | every `ast_select_from` call costs ~6 s before it reads anything, whatever the data: 5.2 s planner, 0.9 s optimizer, 0.19 s execution on a 1246-node table, and the same 6 s on a 1-row table. `PREPARE` does not amortize it (each `EXECUTE` costs the full 6 s), `UNION ALL` of 3 selectors costs 21.8 s, and the macro body is 46,362 characters | verification time is the number of DISTINCT engine calls and nothing else: `verify.execute` caches results per (engine, fixture content, selector) and `pilot.oracle_first_verify` answers the relaxation and distractor gates from the oracle, leaving ~1 engine call per pair |
| #151 (filed elsewhere) | a bare type selector is a prefix match (`with` selects `with_item`, `with_statement`). Measured again on 2026-09-15 from suite 1: Go `import_spec` also returns the 7 `import_spec_list` nodes (23 -> 30) and SQL `column_definition` also returns the `column_definitions` container inside each table (4->5, 8->10, 10->12, 5->6). **Fixed upstream: the prefix match is removed and ships in the next release** (Teague, 2026-09-15) | oracle.py matches types exactly, so it already implements the post-fix semantics; `classify()` tags such a disagreement `pending_engine:type-prefix#151` instead of rejecting the pair. When the release lands, re-verify the pending pairs against the new build -- they should verify unchanged -- and re-check bare-type references (`command` -> `command_name`, `preproc_if` -> `preproc_ifdef`, `lambda` -> `lambda_parameters`) |

## Not filed

**`:docblock` does not exist.** No selector macro or doc mentions it.
`.fn:docblock` raises "unknown pseudo-class"; `.fn:not(:has(:docblock))` raises
"pseudo-classes inside :has(...) are not supported". Both refuse loudly, which is
the right behaviour, so the SPEC §3 example t4-001 ("functions missing
docstrings") cannot be a pair until the predicate exists: `pending_engine:docblock`.

**Captures are silently ignored.** `.fn@f` and `.fn @f` return the same 84 nodes
as `.fn`; `.class .fn@m` returns the same 40 as `.class .fn`. A T9 pair would
execution-match with or without its capture, so captures can't be scored:
`pending_engine:captures`. Unlike `:docblock`, this is silent. It is the #128
class of defect and worth adding there.

**duckent's README overstates today's sitting_duck.** It shows
`WHERE ast_select(node, '.fn:not(:has(:docblock))')` under "Today, with
sitting_duck". There is no row-level `ast_select(node, …)`: `duckdb_functions()`
lists only the table macros `ast_select(source, selector, language)`,
`ast_select_from`, `ast_select_list` and `ast_select_rules`, and `:docblock` is
refused as above.

**`.self` matches nothing in Python.** `.self` and `.fn:has(.self)` return 0.
`selector-examples.md`'s `.class .func:not(:has(.self)):named` therefore has a
vacuous filter (noted in PR #129).

**Attribute filters inside `:has` are refused.** `.fn:has(.str[peek*="x"])`
raises "attribute filters inside :has(...) are not supported", so the tutorial's
full example `.class#UserService .func:has(.call#execute):not(:has(.try)):has(.str[peek*=SELECT])`
errors (noted in PR #129): `pending_engine:attr-in-has`.

**Unknown `.class` names silently match nothing.** `.with_statement`,
`.while_statement`, `.with`, `.decorator` and `.nosuchclass` all return 0 rows
with no error, while an unknown pseudo-class is refused. It is the selector-level
face of #132 (added there as a comment with the numbers below).

## From the stage 1 qualifier (11 models x 40 pairs, card v1)

Pairs that nearly every model missed were read answer by answer before being
blamed on the models:

- **Leading dot on node types** — 18 misses, from all 11 models (`.with_statement`
  7x on t1-p20, `.while_statement`, `.continue_statement`, `.decorated_definition`,
  `.except_handler`).
  The card lists types without a dot but never says the dot is wrong, and the
  engine returns 0 rows instead of an error.
- **`.while` / `.continue` are whole-kind aliases.** "while loops" -> `.loop` (4x)
  or `.while` returns all 56 loops; "continue statements" -> `.jump#continue` (5x)
  returns 0 (jumps have no name). Card v1 does not warn about either.
- **`#name` is the bare name.** "json dumps calls" -> `.call#json.dumps` (6 of 11
  models) returns 0; the callee name is `dumps`. Card v1 does not say so.
- **`.mod >` habit.** 12 misses (8 from GLM-4.7-Flash) prefix `.mod >` where the
  request says nothing about module level; card v1's `.mod > .fn` example is the
  likely source.
- **Three-step chains and filters on the first step** — 19 answers refused by the
  engine, despite the card's "exactly two steps" line.
- **t2-p22 is an NL defect, not a hard pair.** "subcommand parsers being added"
  expects `.call#add_parser`; answering needs argparse trivia (one model guessed
  `add_subparsers`, a different real call). One of 11 models matched. Its NL should
  name the call, the way a developer who knows the code would ask.
- **Genuine discriminators**, where the misses are model errors: t4-p08 "classes
  with a speak method" (6 models returned the methods, `.class .fn#speak`) and
  t4-p29 "conditionals that return or skip" (`.if .jump` returns the jumps).
- **Engine refusal of an equivalent answer**: `.loop:has(.call[name="append"])`
  means `.loop:has(.call#append)` but attribute filters inside `:has` are refused
  (gemma-4-26B-A4B-it, t4-p31).

## From stage 2 (4 models x 109 pairs, card v1 vs card v2)

- **Card v1's examples leaked 7 pairs' exact selectors** (`.fn#main`,
  `.call#print`, `.call#open`, `.fn[params=2]`, `.mod > .fn`, `.import ~ .class`,
  `.fn:has(.call#open)`). All comparisons are on the 102 pairs neither card leaks.
- **A card fix is per-model, not a universal improvement.** v1 -> v2: Qwen3.6-27B
  +4.9 (to 92.2%, level with the Haiku 4.5 control at 91.2%), Haiku -1.0,
  gemma-4-26B-A4B-it -8.8, Qwen3-Coder-30B-A3B-Instruct -4.9. v2 fixed what it
  targeted for every model (t1-p23, t1-p25, t3-p35/36 decorated definitions)
  and over-corrected gemma: its prominent "two kinds of type" section flipped
  gemma into writing guessed node types for plain classes (`.import` ->
  `import_statement`, `.try` -> `try`, `.loop` -> `loop`, `.catch` ->
  `except_handler`), 18 regressions. v2's "#name is the bare name" line turned
  prefix filters into exact names for gemma and Coder (`[name^="update_"]` ->
  `#update`, `[name^="fetch"]` -> `#fetch`).
- **Four more NL defects**, each missed by all four models with the same
  reasonable answer:
  - t2-p18 "recursive glob calls" -> everyone `.call#glob`; the call is `rglob`.
  - t4-p18 "functions that search directories recursively" -> `os.walk` is as
    valid an implementation as `rglob`; the NL can't pick one.
  - t4-p30 "functions that handle exceptions" -> everyone `.fn:has(.try)`; the
    reference is `.fn:has(.catch)`.
  - t4-p35 "with blocks that read a file" -> everyone `:has(.call#open)`; the
    reference is `.call#read`.
  Like t2-p22, these should name what distinguishes the answer.
- **Remaining model errors are mostly about which node is returned** (Coder:
  `.loop .call#print` for "loops that contain a call to print", `.fn:has(.jump)`
  for "functions with no return") and **three-step / misplaced filters** —
  structure, not vocabulary.

## From stages 3 and 4 (per-model cards, 108 pairs)

**Card assignment.** Scored on the 98 pairs every card can be compared on
(leaked and since-reworded pairs excluded):

| model | v1 | v1 retest | v1c | v2 | v3 | card |
|---|---|---|---|---|---|---|
| gemma-4-26B-A4B-it | 85.7 | 86.7 | **86.7** | 76.5 | 78.6 | v1c |
| Qwen3-Coder-30B-A3B-Instruct | 76.5 | 76.5 | **76.5** | 71.4 | 72.4 | v1c |
| qwen3.5-9b-uncensored | — | — | **71.4** | 64.3 | 61.2 | v1c |
| Qwen3.6-27B (stage 2) | 87.3 | — | — | **92.2** | — | v2 |
| Haiku 4.5, control (stage 2) | **92.2** | — | — | 91.2 | — | — |

On all 108 pairs with card v1c: gemma 88.0 %, Coder 77.8 %, the 9B 70.4 %.

- **Run-to-run noise was measured before crediting any card.** Rerunning card
  v1 exactly as stage 2 did: gemma gave 96/98 identical predictions and 1 match
  flip; Coder 88/98 identical and 6 flips (score unchanged). Card changes flipped
  14-28 pairs. gemma's and the 9B's card preferences are well outside noise;
  Coder's 4-5 point gaps are closer to its ~6 % flip rate.
- **Removing the leaked examples cost nothing.** v1c (v1 with its seven leaking
  example selectors swapped for the same constructs on unused names) scores the
  same as v1 for gemma and Coder, so v1's absolute numbers were not being carried
  by the leaks.
- **Each attempt to add guidance hurt the models that did well without it.**
  v2's prominent type rules and v3's lighter version both introduced new errors
  (guessed node types for plain classes; `.loop :has(...)` with a space;
  `.call#json.dumps` right after the card mentioned `time.sleep`). Only
  Qwen3.6-27B gained from v2. Card work beyond v1c is unlikely to pay; the
  remaining errors are the target for tuning.

- **Card v1c's `.import ~ .var` example matches nothing in Python.** `.var`
  (`assignment`) is always a child of `expression_statement` (824 on py-lackpy)
  or `parameters` (289), never of the module, so an import's later siblings are
  `expression_statement`s (`.import ~ expression_statement`: 75, `.import ~ .var`:
  0). It is an illustration, not a scored pair, so no result changes, but it
  shows a shape Python never produces; a later card revision should use
  `.import ~ .fn` or `.import ~ expression_statement`. (Found by the Python
  training-drafting agent.)

**Device lessons folded into `qualify.py`.**
- A chat request that overlapped the NPU embedding job's batches hung 108 s,
  returned 200 with empty content, and the runtime dropped the chat model and
  recreated the embedder (Tiiny beta log). The harness now pauses the embedding
  job for device runs, with a lease guard on the embedding host, and treats an
  empty response as an error.
- The store's `Qwen/Qwen3.5-9B` cannot be downloaded (fails at 0 % within 12 s,
  through three reboots) and the import toolkit catalog is `invalid`, so the
  stock 9B cannot be put on the device either way (beta #070, #071). It was
  removed from the device; the stock weights are on longbottom for tuning.

## From stage 5 (context construction on the device, 108 pairs)

**Engine.** Every stage-5 arm is scored with a pinned copy of the 2026-09-14 18:35
sitting_duck build (`workspace/engine/sd-20260914-1835`, provenance in its
PROVENANCE.md) and the `fix/127-combinator-steps` macros (28c60f39), the pairing
`qualify.py oracle` scores at 100 % with every first distractor at 0 %. The same build
with main's `css_selectors.sql` (16785fe1) returns 0 rows for every two-step selector
(`.try .call` 0 of 11, `.class#Animal .fn` 0 of 5), so an early stage-5 summary showing
T3 0/31 was the engine, not the models. The extension had also changed since stage 4,
so stage-5 numbers are compared only with the same-session card v1c control below,
never with stages 1-4.

**Arms**, all card v1c plus: nothing (control); ten static examples from verified
Python training pairs, one per FINDINGS error class (`card_v1c_fewshot.md`); the
eight Python training pairs nearest each request by TF-IDF (`--retrieve 8`); the
same with other languages' semantic-class-only pairs admitted (`--retrieve-portable`).
No arm shows any eval pair its own answer (`meta.leaked_ids` empty).

| model | control | static 10 | retrieve 8 | retrieve 8, portable |
|---|---|---|---|---|
| gemma-4-26B-A4B-it | 88.0 | **91.7** (+5 -1) | 90.7 (+7 -4) | 85.2 (+4 -7) |
| Qwen3-Coder-30B-A3B-Instruct | 76.9 | **83.3** (+14 -7) | 80.6 (+8 -4) | 75.0 (+9 -11) |
| qwen3.5-9b-uncensored | 67.6 | 68.5 (+7 -6) | **71.3** (+10 -6) | 68.5 (+12 -11) |

(+gained -lost match flips against the control.)

- **Read against measured noise** (stage 3: gemma 1 flip in 98, Coder 6). gemma's
  gains from either Python-only arm are outside noise. Coder's +6.5 from static
  examples comes with 21 flips, so its direction is likely but its size is not
  settled. The 9B's +3.7 from retrieval has no noise measurement to be judged
  against. No arm is best for every model, as with the stage-2 cards.
- **What examples fix** is the FINDINGS list: `.call#json.dumps` -> `.call#dumps`,
  `.class .fn#speak` -> `.class:has(.fn#speak)`, `.loop :has(...)` losing its space,
  dotted node types losing the dot. **What they break** is structure: an added step
  (`.class#User .fn#reset` for "the reset function"), `>` for a descendant, and once
  a node type for a class (Coder: `.if` -> `if_statement`).
- **Other languages' examples mislead, even restricted to semantic classes.** The
  portable pool fills 721 of 864 example slots and costs gemma 2.8 and Coder 1.9
  points: `.fn#constructor` for `__init__` (JavaScript/Java), `[name^="print"]` for
  `#print`, `+` where `~` is meant. Example pools stay per language; routing a
  request to its language's examples or card via sitting_duck's language detection
  is acceptable (Teague, 2026-09-14).
- **Scoring cost.** On this build one `ast_select_from` takes ~16 s on these small
  fixtures and a fixture parse ~5 s, so scoring 165 predictions single-process took
  ~45 min. `verify.execute` now shards across `ASTCSS_EXEC_JOBS` processes.

**Local baseline for tuning.** Stock `Qwen/Qwen3.5-9B` (the tuning base), NF4 4-bit
with float16 compute on the 2080 Ti, card v1c, greedy, thinking off
(`tune/local_generate.py`): **64.8 %** (T1 15/21, T2 20/25, T3 14/31, T4 21/31), median
3.97 s per request in batches of 8. Two-step selectors are its weak tier. It is not
directly comparable with the device's uncensored 9B (67.6 %): different weights,
quantization and runtime.

**Context arms on the local stock 9B** (same prompts as the device arms, greedy, NF4):

| arm | match | T1 | T2 | T3 | T4 | +flip | -flip |
|---|---|---|---|---|---|---|---|
| no card | 0.0 | 0/21 | 0/25 | 0/31 | 0/31 | | |
| card v1c | 64.8 | 15/21 | 20/25 | 14/31 | 21/31 | | |
| static 10 | **75.9** | 15/21 | 22/25 | 21/31 | 24/31 | 15 | 3 |
| retrieve 8 | 75.0 | 15/21 | 22/25 | 19/31 | 25/31 | 14 | 3 |

- Without the card the stock 9B answers in prose ("I don't have access to any class...");
  the card is what makes it answer with selectors at all.
- Both example arms add ~10 points, mostly two-step selectors (T3 14 -> 19-21):
  invented syntax goes (`.call:has(ancestor(.try))` -> `.try .call`), `:has` wraps the
  right node (`.class .fn#speak` -> `.class:has(.fn#speak)`), and the dotted-node-type and
  `.call#json.dumps` errors are fixed. The losses are `+`/`~` and an added `.try` step.
- Unlike the device's larger models, the stock 9B gains as much from static examples as
  from retrieval.

**Prompt format facts, verified.**
- Thinking is off in both runners. Locally the chat template is rendered with
  `enable_thinking=False` (an empty `<think></think>` block); no stock-9B response
  contains think tags and 88 of 108 answers are 3-10 tokens. On the device
  `chat_template_kwargs.enable_thinking=false` is honoured: gemma and the uncensored
  9B return 0 reasoning characters at ~0.56 s median.
- The Qwen3.5 chat template trims every message's content, so card_v1c.md's trailing
  newline never reaches the prompt. `tune/prompting.py` renders each prompt shape once
  and substitutes stripped text, checked byte-identical to `apply_chat_template` on 36
  cases (dataset rows from all three variants, padding, quotes, unicode).

**Device.** The broken store entry for `Qwen/Qwen3.5-9B` (status `error`, 0 %,
`toolkit_size` 0, no import metadata) was removed with `tiiny rm` after unloading
every model; the imported `qwen3.5-9b-uncensored` (its own HF weights and
`qwen3.5-9b` toolkit) loaded and answered afterwards, so nothing it depends on was
shared. The clean re-download still fails, device-side: calling
`POST /api/v1/models/Qwen%2FQwen3.5-9B/download/stream` directly shows `init`, then
`downloading` with `total_bytes` 0, then after ~11 s `status: error`,
`stage: failed`, "Model Qwen/Qwen3.5-9B download failed." and no other detail. The
package size is never learned, so the store fetch fails before any bytes move (beta
#070 again); unloading every model first does not change it. Separately, `tiiny
download` (CLI v0.0.3) deadlocks on that failure event (`fatal error: all goroutines
are asleep`, a goroutine blocked on a channel send in `DownloadModel.func1`) instead of
printing the error. The stock 9B stays local-only.

Store downloads fail for every model tried, not just the 9B. `Qwen/Qwen3-4B-Instruct-2507`,
the only store chat model at or under 4B, failed the same way at 21:03 (all models
unloaded first): `downloading` at 0/0 bytes, then after ~11 s `status: error`, "download
failed", nothing else. Ruled out, each checked: device storage (545 GB free), device
internet (the import inspect still fetches Hugging Face metadata), loaded models (none),
the local API key and the account session (`tiiny auth info` answers). What remains is
the device's store/catalog service -- the same side that reports the import toolkit
catalog `unavailable`. Worth a beta report together with the CLI deadlock.

**Small model on the device, untuned.** `Qwen/Qwen3-8B` (already downloaded), card v1c,
thinking off: **51.9 %** on 108 pairs (T1 14/21, T2 18/25, T3 6/31, T4 18/31), 0.51 s
median. One request stalled ~103 s and returned empty; the retry answered in 0.36 s.
Its 83.3 % "exec" is inflated: prose and malformed first lines still execute, because
unknown selector parts are ignored silently (sitting_duck #128).

Context arms on the same Qwen3-8B (store downloads failing, it is the smallest chat model
on the device), same session and engine, flips against its card v1c control:

| arm | match | T1 | T2 | T3 | T4 | +flip | -flip |
|---|---|---|---|---|---|---|---|
| card v1c | 51.9 | 14/21 | 18/25 | 6/31 | 18/31 | | |
| static 10 | 57.4 | 10/21 | 20/25 | 10/31 | 22/31 | 11 | 5 |
| retrieve 8 | **64.8** | 15/21 | 21/25 | 10/31 | 24/31 | 16 | 2 |

- Without examples Qwen3-8B anchors selectors at the module (`.mod > .try > .call`,
  `.mod > .import`) -- the stage-1 `.mod >` habit. Both arms mostly remove it.
- Retrieval also fixes `:has` placement (`.fn .call#rglob` -> `.fn:has(.call#rglob)`,
  `.class[name*="speak"]` -> `.class:has(.fn#speak)`) and `.call#json.dumps` ->
  `.call#dumps`, and its two losses are both T4. Static examples cost four T1 pairs by
  decorating plain classes (`.comp` -> `.comp#list`).
- Retrieval's +13.0 (16/2) is the largest context effect measured in stage 5 or 6, on
  the weakest device model. No run-to-run noise measurement exists for Qwen3-8B.

## From stage 6 (local QLoRA learning curve, Qwen3.5-9B NF4, 108 pairs)

LoRA r=16 on all linear layers, 2 epochs, no system prompt: the request goes in bare and
the selector comes out. Training data is every verified training pair in all nine
languages, capped at 8 per (request template, selector shape); the 25 % and 50 % subsets
nest inside the full set and share its 85 validation pairs. 1.05-1.13 s per row on the
2080 Ti, 8.1 GiB peak; the full set is ~40 min per epoch. Scored with the pinned engine.

| training pairs (incl. 85 val) | shapes | val loss e1 / e2 | match e1 | match e2 |
|---|---|---|---|---|
| 278 (25 %) | 147 | 0.882 / 0.719 | 43.5 | 54.6 |
| 457 (50 %) | 212 | 0.557 / 0.554 | 61.1 | 70.4 |
| 820 (100 %) | 297 | 0.378 / 0.363 | **74.1** | 70.4 |

Same model, untuned: no card 0.0 (it answers in prose), card v1c 64.8, static 10 examples
75.9, retrieval 8 75.0.

- The adapter with a 7-token prompt (74.1) matches the untuned model carrying the
  ~2.5 KB card plus examples (75.9; +16/-18 flips), at half the latency (0.27 s vs 0.56 s
  median). Against the card alone it is +9.3 (+26/-16).
- The curve is still rising at the full set (43.5 -> 61.1 -> 74.1 at epoch 1), so more
  verified pairs should still help. The second epoch helps small sets and not the full
  one (74.1 -> 70.4, 4 pairs, one run each, no noise measurement).
- Gains are structure the card never taught: `:has` versus a descendant step
  (`.loop :has(.jump)` -> `.loop .jump`, `.if .jump` -> `.if:has(.jump)`), bare callee
  names (`.call#json.dumps` -> `.call#dumps`), naming the enclosing function
  (`.fn:has(.call#rename)`); T3 goes 14 -> 23/31.
- **Most losses are other languages' vocabulary.** Of the 16 lost pairs, 9 use another
  language's node types or names: `catch_clause` and `throw_statement` (Java),
  `if_statement` (Java/Bash/Go), `.call#log` (JavaScript's `console.log`, three pairs),
  `.fn#new` (Rust). Python is 297 of the 2,205 training rows, and nothing in a bare
  request says which language it is. Python's training rows contain no `.call#print`,
  no `.catch` and no `[params=N]` (the other two losses, card features the adapter never
  saw); two more are raw `comprehension` for `.comp`. T4 drops 21 -> 19/31.
- Next: name the language in the request (`[python] ...`; sitting_duck's classifier can
  supply it when serving) on the same pairs, and see whether the vocabulary losses go.

### Stage 6: every other chat model on the device, three context arms

Same 108 pairs, pinned engine, one model at a time with arms back to back (2026-09-14
21:29 -> 09-15 04:09). Thinking off where it can be switched off; gpt-oss at
`reasoning_effort` low (4,000-token budget); Qwen3-30B-A3B-Thinking always thinks
(8,000), so it ran the control only.

| model | card v1c | static 10 | retrieve 8 | med s (control) |
|---|---|---|---|---|
| **Qwen/Qwen3.6-27B** | 88.9 | 92.6 (+5 -1) | **93.5** (+6 -1) | 2.1 |
| Qwen/Qwen3-30B-A3B-Thinking | 83.3 | -- | -- | 35.5 |
| Qwen/Qwen3-30B-A3B-Instruct | 74.1 | 76.9 (+7 -4) | 78.7 (+9 -4) | 0.41 |
| Qwen/Qwen3.5-35B-A3B | 75.0 | 77.8 (+8 -5) | 77.8 (+10 -7) | 0.57 |
| Qwen/Qwen3-Coder-30B-A3B-Instruct-Turbo | 71.3 | 78.7 (+16 -8) | 76.9 (+11 -5) | 0.57 |
| openai/gpt-oss-20b | 65.0* | 65.7* | 75.2* | 6.4 |
| openai/gpt-oss-120b | 66.7 | 68.5 (+12 -10) | 73.1 (+13 -6) | 10.2 |
| zai-org/GLM-4.7-Flash | 55.6 | 71.3 (+20 -3) | 70.4 (+20 -4) | 1.17 |

\* over 103-105 answered pairs: 3-5 requests per arm spend the whole reasoning budget
and return no answer after ~142 s, on the retry too.

- **Qwen3.6-27B with retrieval (93.5) is the best result so far**, above gemma-4-26B
  (91.7, static examples, stage 5): T2 25/25, T3 29/31, T4 29/31. It is also the
  slowest non-reasoning model (2-2.7 s per answer; gemma ~0.5 s).
- Examples help every model; the weaker the control, the larger the gain (GLM +15.7,
  Qwen3.6 +4.6). Retrieval is never worse than static examples by more than 2 points.
- Reasoning does not pay here: gpt-oss-120b at low effort is below the non-thinking
  30B-A3B-Instruct at 25x the latency, and the always-thinking 30B-A3B (83.3) is 9 points
  above its Instruct sibling at ~85x the latency.
- The Turbo Coder is not the stage-5 Coder (`Qwen3-Coder-30B-A3B-Instruct`, 76.9 control):
  71.3 control here, different package, so not a noise estimate.

### Stage 6b: Qwen3.5-0.8B (float16 weights + LoRA), same 820 pairs

| arm | match | T1 | T2 | T3 | T4 | med s |
|---|---|---|---|---|---|---|
| untuned, no card | 0.0 | 0/21 | 0/25 | 0/31 | 0/31 | 0.21 |
| untuned, card v1c | 26.9 | 10/21 | 12/25 | 5/31 | 2/31 | 0.27 |
| LoRA, no system prompt, e1 / e2 / e3 | 63.9 / 65.7 / 69.4 | 17/21 | 17/25 | 25/31 | 16/31 | 0.37 |
| LoRA, per-language card as system prompt, e1 / e2 | 69.4 / **81.5** | 19/21 | 16/25 | 25/31 | 28/31 | 0.17 |

(tier columns are the last epoch)

- **The 0.8B trained with its language's card beats every local 9B arm** (81.5 vs 75.9 for
  the untuned 9B with card + examples, 74.1 for the 9B no-card adapter), at 1.8 GiB
  peak and 0.72 s/row training. It is below the best device arm (gemma-4-26B, card +
  examples, 91.7). One run per arm; no noise measurement.
- The card arm trains on all nine languages with train/cards/card_<lang>.md and is asked
  with card_v1c.md (identical to card_python.md), so the card also tells the model
  which language it is answering. Card vs no card on the same pairs is +12.1 at the best
  epoch and T4 16 -> 28/31 -- consistent with the stage 6 language-vocabulary losses,
  but it confounds the card's content with the language cue. Stage 6e's `[python]` tag
  separates them.
- Training speed was the same with and without the card on the 0.8B (~27 min per epoch
  for 2,205 rows).
- Some runs generate to the 48-token limit after the selector (`.try\nassistant\n.try\nuser...`).
  Not the model: every Qwen3.5 `config.json` names `<|endoftext|>` (248044) as eos, while
  a chat turn ends with `<|im_end|>` (248046), so `generate` ran past the end of the
  turn and the next turn's role names decode as text. Scoring takes the first line, so
  match is unaffected; latency is inflated in every local run before 2026-09-15 05:10.
  local_generate.py now stops on both ids (a 4-pair check: 3-9 tokens per answer).

### Stage 6e: naming the language instead of sending the card (0.8B)

Same 820 pairs and schedule as the 0.8B no-card adapter, with every request prefixed by
its language (`[python] calls to sleep`; tune/prompting.tag_request), asked with
`[python]` and no card:

| 0.8B arm | e1 | e2 | e3 |
|---|---|---|---|
| no prompt (6b) | 63.9 | 65.7 | 69.4 |
| language tag | 66.7 | **74.1** | 74.1 |
| per-language card (6b) | 69.4 | **81.5** | -- |

- The tag is worth +4.6 to +8.3 over the bare request at the same epoch, mostly T4
  (16 -> 22-25/31): about half of the card's gain. The card's content is worth the rest
  (-7.4 for the tag against the card, +4/-12 flips at e2).
- A tag costs ~3 tokens and the card ~700, so where latency or context matter the tag is
  the cheaper half; where they don't, the card still wins on the 0.8B.
- **Qwen3.5-9B NF4 with the language tag: 75.0 / 77.8** (e1 / e2; T1 18/21, T2 18/25, T3 25/31,
  T4 23/31 at e2), +3.7 over the 9B no-card adapter at e2 (74.1) and only 3.7 above the 0.8B
  tag arm (74.1) for 11x the parameters; below the 0.8B trained with the card (81.5). The 9B
  card run was paused on 2026-09-15 to give the GPU to the 0.8B work.
- Generation stops at `<|im_end|>` in these runs: 0.08 s per answer on the 0.8B.

### Stage 6c: the Qwen3.5 size ladder, trained with the per-language card

Same 820 pairs and card format as the 0.8B arm above (train/cards/card_<lang>.md in
training, card_v1c.md when asked), LoRA r=16, 2 epochs, pinned engine. The ladder was
switched from the no-card format to this one before it started, on the stage 6b result.

| model | untuned, no card | untuned, card v1c | trained e1 / e2 | per epoch, peak |
|---|---|---|---|---|
| Qwen3.5-0.8B float16 | 0.0 | 26.9 | 69.4 / 81.5 | 27 min, 1.8 GiB |
| Qwen3.5-2B float16 | 0.0 | 30.6 | 80.6 / 82.4 | 27 min, 4.1 GiB |
| Qwen3.5-4B NF4 | 0.0 | 57.4 | 86.1 / **89.8** | 49 min, 3.8 GiB |
| Qwen3.5-9B NF4 | 0.0 | 64.8 | paused (language tag: 75.0 / 77.8) | ~75 min (probe), 8.5 GiB |

- **The trained 4B (89.8; T1 21/21, T2 21/25, T3 28/31, T4 27/31) is within 3.7 of the
  best device result**, Qwen3.6-27B with retrieval (93.5). Pair by pair: 94 both right,
  4 both wrong, 7 only the 27B, 3 only the 4B. The 27B's extra wins are mostly
  prefix filters the 4B turns into exact or wrong names (`.fn#update` for
  `.fn[name^="update_"]`, `.call#fetch`, `.call[name^="_add_"]` for `^="add"`), plus
  `if_statement` for `.if` and `.fn#run` for `.fn#main`. The 4B's three are node types
  the 27B dotted into non-classes (`.while`, `.continue`, `.decorated_definition`).
- Training lifts every size far above its untuned card score; the gain shrinks with size
  (0.8B +54.6, 2B +51.8, 4B +32.4), and 0.8B and 2B land together (81.5, 82.4).
- One run per arm; the stage-3 flip rates (1-6 per 98) are the only noise reference.

### Stage 6d: Qwen3-4B-Instruct-2507 locally (NF4, untuned)

The store download to the device fails (above), so it ran on the 2080 Ti: card v1c
55.6, static 10 examples 66.7 (+15 -3), retrieval 8 66.7 (+16 -4); examples take T3
from 9 to 15-16/31. Below Qwen3.5-4B trained (89.8) by 23 points.

### Stage 7a/7b: seed noise, and 343 more pairs on the 0.8B

Same recipe as the stage 6b card arm (per-language card, cap 8, LoRA r=16, 2 epochs).
7a changes only the seed. 7b keeps seed 17 and appends the selector-first pilot's 343
engine-verified pairs (T1-T4, gemma-worded, wording not back-translation filtered;
workspace/sfgen/pairs/accepted-sf-p1.jsonl).

| 0.8B arm | e1 | e2 | e2 T1 | T2 | T3 | T4 |
|---|---|---|---|---|---|---|
| 820 pairs, seed 17 (6b) | 69.4 | 81.5 | 19/21 | 16/25 | 25/31 | 28/31 |
| 820 pairs, seed 18 (7a) | 78.7 | **82.4** | 19/21 | 17/25 | 25/31 | 28/31 |
| 820 + 343 pairs, seed 17 (7b) | 74.1 | 79.6 | 19/21 | 17/25 | 24/31 | 26/31 |

- **Seed noise is large after one epoch and small after two**: the seeds differ by 9.3
  at e1 and by 1 pair at e2. Single-run e1 comparisons in stages 6b-6e are not
  evidence of anything; e2 comparisons within ~2 points are not either.
- **The 343 pairs did not help**: e2 is 1.9 below the same seed (+5 -7 flips) and 2.8
  below seed 18 (+4 -7), losing T3/T4 pairs. That is within about two pairs of noise,
  so "no gain" is the safe reading rather than "harm". The pilot pairs are the same
  T1-T4 shapes the 820 already cover, so more of the same may simply be saturated at
  this size; the tier-5 suite tests whether new shapes do better.

### Stage 7c: tier-5 baselines before any tier-5 training

The 55 tier-5 eval pairs (eval_t5, t5-b1 + t5-b2), asked with card_t5.md (card v1c + the
tier-5 vocabulary block). The trained adapters are the stage 6b/6c/7a ones: they never
saw a tier-5 selector or the tier-5 block. Pending pairs are scored by documented semantics.

| model | tier-5 match | exact | med s |
|---|---|---|---|
| Qwen3.5-0.8B untuned | 7.3 | 3.6 | 0.20 |
| Qwen3.5-0.8B trained, seed 17 / seed 18 | 34.5 / 30.9 | 10.9 / 9.1 | 0.24 |
| Qwen3.5-2B trained | 38.2 | 14.5 | 0.34 |
| Qwen3.5-4B NF4 trained | **67.3** | 34.5 | 0.84 |
| Qwen3.5-9B NF4 untuned | 60.0 | 38.2 | 0.83 |

- **Tier 5 separates sizes far more than tiers 1-4 do**: on the 108 pairs the trained
  0.8B/2B/4B score 81.5/82.4/89.8; on tier 5 they score 31-35/38/67. The untuned 9B
  (64.8 on the 108 with the card) is within 7 points of the trained 4B here. New
  vocabulary read from a card is what the small models cannot do yet.
- **The longer card costs the trained 0.8B 8.3 points on the 108 pairs** (82.4 -> 74.1,
  +1 -10 flips, losses in every tier) with the same adapter. A model trained on one card
  is brittle to prompt drift, so the tier-5 training runs must train with the card they
  are asked with (train/cards/v2 = card + tier-5 block) and be scored on both evals with
  that card; the 82.4 baseline was measured with card v1c and is not directly comparable.

### Stage 7d: training with the tier-5 card, no tier-5 pairs (0.8B)

Stage 6b's recipe and 820 pairs (pre-audit), seed 17, with train/cards/v2 (card + tier-5 block)
as the system prompt in training; asked with card_t5.md (identical to the v2 python card).

| 0.8B, e2 | trained with | asked with | 108 pairs | T1 | T2 | T3 | T4 | tier 5 |
|---|---|---|---|---|---|---|---|---|
| 6b | card v1 | card v1c | **81.5** | 19/21 | 16/25 | 25/31 | 28/31 | -- |
| 7c | card v1 | card_t5 | 74.1 | 18/21 | 16/25 | 22/31 | 24/31 | 34.5 |
| 7d | v2 (card + tier-5 block) | card_t5 | 75.9 | 16/21 | 17/25 | 22/31 | 27/31 | 29.1 |

- **The tier-5 vocabulary in the card does not teach tier 5 to the 0.8B**: 29.1 is no better
  than the adapters that never saw the block (34.5 / 30.9). Reading new syntax off a card is
  what the 0.8B can't do (7c); training on the card doesn't change that without examples.
- **And the block costs the basic tiers ~6 points** (81.5 -> 75.9, mostly T1 and T3), about 6
  pairs against ~1 pair of e2 seed noise. The extra ~700 tokens of vocabulary compete with
  the vocabulary the 108 pairs use.
- So the tier-5 run should not simply swap in the v2 card. Arms worth running once the suite
  is filtered: card v1 + tier-5 pairs (vocabulary from examples only), v2 card + tier-5 pairs,
  and a short tier-5 block. The 108-pair score is the guard against losing the basic tiers.

## From the generation pilot (device models write training pairs from source files)

gemma-4-26B-A4B-it was given one training-fixture file at a time (10 Python, 10 Rust, 10
JavaScript; 2-12 KB each) with the language card, the brief's rules, the fixture's name
inventory and a tier mix weighted to T3/T4, and asked for 8 candidates per file.
Wording failures went back to it twice with the exact shared words. Survivors went
through pilot.py's training gates, then Qwen3-Coder-30B-Turbo translated each request
back to a selector from the card alone. Scripts: workspace/gen_pilot.py (gitignored).

| stage | candidates left | share |
|---|---|---|
| generated | 238 | 100 % |
| pass the wording gates as generated | 50 | 21 % |
| ... after two repair rounds | 103 | 43 % |
| pass the engine gates | 30 | 13 % |
| Coder reproduces the node set from the request or a paraphrase | 26 | 11 % |

By tier: T2 18/77, T3 7/50, **T4 5/111**. Device time 2,590 s (generation 1,257,
repair 1,333) plus 1,128 s of verification: ~2.5 min per surviving pair.

- **Below the 30 % bar set for scaling, and the survivors are the easy shapes.** 16 of
  the 30 are `.fn#name` or `.call#name`; 12 distinct shapes in all, 4 of them new to
  the training set (`.fn#_ .var`, `.fn .call#_`, `.if:has(.call#_)`, `.fn#_ .member`).
  The candidates had 77 shapes; the hard ones are what the gates removed.
- **Wording is the largest loss.** 188 of 238 as generated reuse the name and the noun
  in all three texts ("the Hole class" / "find the Hole class"); repair with the
  shared words listed recovers 53, and 135 still fail.
- **The model cannot see match counts.** Bounds rejected 36: common names across the
  whole fixture (`.call#get` 106, `.call#getattr` 141), generic T4s
  (`.fn:not(:has(.try))` 139), and selectors that match nothing (`.if:has(.assignment)`,
  `.fn#copy .call#copy`). Generic T4s also collide with the eval: 11 candidates were
  exactly an eval answer (`.fn:has(.try)`, `.fn:has(.call#print)`, `.fn:has(.loop)`),
  and 17 duplicated node sets already in training.
- **Back-translation is a real semantic check.** It flagged `.call#parse_query` asked as
  "the parse_query function" -- a request/selector mismatch no execution gate can see --
  along with three that read correctly (`.fn .call#json`, "functions that call json").
- Implication: generate the selector deterministically from the engine (names and
  shapes with 1-50 matches, load-bearing steps and no eval or training collision checked
  before any model call) and ask the model only for the wording. That removes every
  engine-stage loss above and lets the shape mix be chosen instead of hoped for.

## From tier 5 and the larger training suite (2026-09-15)

**Documented semantics as the reference (`oracle.py`).** Tier 5 needs features the engine
gets wrong today, and the decision (Teague) is to write pairs against the documented meaning
and patch the engine later. `oracle.py` computes that meaning in Python over the engine's own
node table, with class membership taken from `ast_select_from` per class. Validation: all 343
engine-verified selector-first references (T1-T4, every combinator) reproduce exactly; 11
documented cases from the filed issues' repro file all match. Where the engine disagrees, a
pair is `pending_engine:<issue>` only if a filed issue explains the difference, otherwise it
is rejected -- which is how #152 was found (`:called-by` looking through lambdas).

**Tier-5 eval (`eval_t5/`, 47 pairs).** Several constraints on one node, receivers,
`:calls` / `:called-by` / `:is-called`, references and exports, `:scope(selector)`,
decorators and return types, on the two eval fixtures; 35 selectors generated, 12 picked by
hand; wordings hand-written under the strict paraphrase rule. 34 are engine-verified; 13 are
pending on #145, #147, #148, #150 and #152 and scored by the documented semantics
(`qualify.py --pairs-dir eval_t5`). Kept outside `pairs/` so the 108-pair numbers stay
comparable. Teague's example query (`.class#UserService .fn:has(.call#execute):not(:has(.try))`)
could not be a pair: on this fixture the `:not(:has(.try))` step changes nothing.

**Suite 1 (`tune/gen_pairs.py`).** 4,601 candidates over all 20 training fixtures and nine
languages (T5 2,299; 1,847 distinct shapes, 3,986 new to training). SQL and Bash get few tier-5
families: no receivers, call graph or modifiers there.

**How well device-model wordings read back.** Qwen3.6-27B translated 635 gemma wordings of 215
selector-first pairs back to selectors (the run was stopped before the end): 148 of 215 pairs
(69 %) had at least one wording come back to the same node set; per wording 62-66 %. Names and
prefix filters 52/52; siblings and `>` 50/72; `:has` over node types 36/72; bare node types 1/7.
The misses read correctly ("loops that contain at least one continue statement"): these are the
shapes even the strongest reader gets wrong, not bad wordings.

**Node to selector (`Tree.selector_for`).** A DevTools-style "copy selector": the node's classes,
type, name, receiver, parameter count and return type, plus two-step selectors anchored on the
nearest named function or class; exactly-one-match first. On 40 sampled named nodes per fixture
a unique selector exists for 82 % (py-variety), 70 % (rs-magic), 62 % (py-blq), 58 % (js-messe);
11 of 12 unique selectors return exactly that node on the engine (the miss: bare type prefix
match, #151). What stays ambiguous is repetition inside one scope (`append` x66 in one function):
two steps and no file or line attribute cannot separate them.

**Running long jobs.** Claude Code's background-task guard killed every long job at 09:05-09:07
for "low memory" while the kernel reported ~100 GB available, no cgroup limits, no OOM events and
near-zero memory pressure; committed memory was ~85 of 87 GB (many MCP servers, OCR workers,
CUDA reservations). The one real memory fault was ours: `verify_batch` ran engine checks across
many fixtures per process (fixed: one fixture at a time). Long chains now run as systemd user
units (`astcss-stage7`, `astcss-suite1`; `systemctl --user stop <unit>`), logging to
`workspace/logs/unit-*.log`.

## Request audit: requests that don't determine their selector (2026-09-15)

The verifier checks a selector against its fixture, never whether the request carries what
the selector needs. The 0.8B's misses showed the cost: it answered "starts with add" as
`[name^="_add_"]` and "start with get_" as `^="_get_"` (4 eval pairs, 3.7 points), and
python-b1 had taught it, e.g. "functions whose names start with cmd" verified as
`.fn[name^="_cmd_"]` because the fixture's functions are `_cmd_*`. The drafting brief's
paraphrase rule (no two texts share half their content words) pushed drafters to drop the
name from paraphrases, and nothing checked that the request still named it.

`audit_pairs.py` runs three passes over every set (training, the sf-p1 pilot, both evals, and
suite1's generated wordings):

| defect (audit_pairs.request_reasons) | training pairs | texts | example |
|---|---|---|---|
| prefix/suffix claim that isn't the filter value: falsified | 6 | 12 | "start with parse" for `^="_parse_"` |
| the same, separator missing ("narrower") | 9 | 15 | "end in bind" for `$="_bind"` |
| name filter value stated in no form | 37 | 59 | "which functions implement parsing?" for `^="_parse_"` |
| a name defined in the fixture described only by its role | 47 | 112 | "the function that deletes a path" for `.fn#do_rm` |
| "right after"/"immediately" worded against `~` | 3 | 4 | "which fields come right after a status field?" |
| a request pointing outside itself | 2 | 2 | "which fields does that table define?" |

90 training pairs (202 texts) were affected; a pair can carry more than one defect. Well-known APIs described by role
("write to the console" for `print`, "set up command line arguments" for `add_argument`)
are not defects: the eval asks them the same way, and a reader who can't see the fixture
still recovers the name. Substring matches don't count as naming a literal ("deletion" does
not name `del`, "reconciling" does not name `recon`).

- **Eval (text 0, the text the model is asked):** one flag, t2-p24 "the update functions"
  for `.fn[name^="update_"]` (exact name or prefix?). Teague's convention for such
  ambiguity: return both, as a CSS/jQuery selector would, so the reference is the union of
  `.fn#update` and `.fn[name^="update_"]`. On repo-small-py no function is named `update`
  (update_file, update_index, update_sql_macro, update_test_file), so the union is the
  current node set and the pair stands unchanged; `.fn#update` selects nothing and stays wrong. Paraphrases the eval never
  asks have ~20 role-only texts. eval_t5: none.
- **sf-p1:** two generated questions with inverted polarity ("Do any raise statements contain
  a loop?" for `.throw:not(:has(.loop))`); sf-p1 is not in any planned dataset.
- **suite1 wordings:** no prefix/suffix or literal defects (the glosses quote the value); one
  selector worded "immediately following" for `~` in all three texts.

Fixes:
- `train/audit/reword-r1.json` rewords the 202 texts to state the literal (typed or spoken:
  "the do_rm function", "where is the run user function defined?");
  `train/audit/apply_reword.py` retires the 90 originals to `train/pairs/retired.jsonl` and
  writes them as `<id>-a1` in `train/candidates/audit-r1.jsonl`.
- `train/audit/prefix_contrast.py` adds 184 literal prefix/suffix candidates from real fixture
  names (150 with no underscore; contrasts on one stem like `^="print"` / `^="print_"`),
  batch prefix-c1.
- `audit_pairs.request_reasons` is now a gate: pilot.py rejects training candidates that fail
  it, and gen_pairs' filter stage drops such wordings before they reach a dataset.
- The reworded ids change 90 pairs' validation membership (the split hashes the id).

## Taxonomy observations (no defect claimed)

- `.loop` includes comprehension `for_in_clause`, and `.if` includes `if_clause`,
  `elif_clause` and `else_clause`. The docs say "all loops" and "all
  conditionals", so this is consistent, but "every loop" reads narrower than the
  engine's answer. Pair NL was written against the engine's meaning.
- `.fn` includes `lambda`.
- The engine tolerates whitespace after `#`: `.call# print` matches `.call#print`.
- `.call#json.dumps` executes and returns 0: the name filter compares against the
  bare callee name (`dumps`), and the `.dumps` part is dropped silently (#128).
  Models do write this spelling (Qwen3-8B, smoke run), so it will show up as a
  common miss rather than an error.

## Verification speed: what a batch actually costs (2026-09-15)

Measured on the pinned engine and on a clean build of sitting_duck main (caa35ff), CLI timings:

| what | time |
|---|---|
| `read_ast` of a 1246-node file | 0.03 s |
| `read_ast` of the whole c-duckhts fixture | 0.16 s |
| any `ast_select_from` call | 6.0-6.4 s |
| the same call on a 1-row table | 6.1 s |
| `PREPARE` of that call, then each `EXECUTE` | 6.0 s, then 6.2 s each |
| `UNION ALL` of 3 selectors | 21.8 s |
| `EXPLAIN` of one call | 39 s |

JSON profiling puts 5.2 s of a 6.3 s call in the planner (binding is 0.05 s of that) and 0.9 s
in the optimizer; execution is 0.19 s of CPU. `ast_select_from` is a table macro with a
46,362-character body. Filed as **sitting_duck #160**: the cost is per call, not per row, so
verification time is the number of distinct engine calls and nothing else.

Two changes followed, and both were validated by replaying already-verified batches:

- **Result cache** (`verify.execute`): identical (fixture, selector) queries run once, and
  results persist in `workspace/cache/engine-results.sqlite` keyed on content hashes of the CLI,
  extension and macros, the fixture's files, and the selector. Deterministic errors are cached;
  timeouts, missing output and memory errors are not. `ASTCSS_ENGINE_CACHE=0` turns it off.
  The verifier self-test: 28.8 s cold, 2.0 s warm, identical output.
- **Oracle-first gates** (`pilot.oracle_first_verify`, the default for training batches): the
  engine runs each reference selector; relaxations and distractors are answered from
  `oracle.Tree` where the oracle reproduces the engine's reference exactly and the check
  carries no feature with a filed engine defect (`oracle.ISSUES`). Everything else still goes to
  the engine -- whole pairs when the oracle cannot parse the selector, when the fixture has no
  oracle cache, or when the reference disagrees; single checks otherwise. `--gates=engine`
  forces the old path, and the eval set (root == HERE) keeps it.

Replay of three batches on the engine that verified them, same verdicts and same node sets:

| batch | candidates | before | after | oracle-answered checks |
|---|---|---|---|---|
| templates-c1 | 8 | (part of a 7-min run) | 47 s | 20 of 22 |
| audit-r1 | 90 | 16 m 41 s | 4 m 57 s | 252 of 288 |
| prefix-c1 | 184 | 41 m 52 s | 4 m 36 s | 658 of 658 |


### Stage 8: what the prompt is still worth to a trained 0.8B (2026-09-15)

No training: the stage 6b (seed 17) and 7a (seed 18) adapters, asked with different prompts.
`train/cards/card_python.md` is byte-identical to `card_v1c.md`, so the controls were asked with
exactly the prompt they were trained with. The k-NN rows are not a model: for each eval request,
the nearest training request by TF-IDF (tune/context.Retriever) and its selector copied verbatim.

| arm | 108 pairs | vs control | flips | T1 | T2 | T3 | T4 |
|---|---|---|---|---|---|---|---|
| card v1c, seed 17 (6b control) | **81.5** | -- | -- | 19/21 | 16/25 | 25/31 | 28/31 |
| card v1c, seed 18 (7a control) | **82.4** | -- | -- | 19/21 | 17/25 | 25/31 | 28/31 |
| card_v1c_fewshot, seed 17 | 79.6 | -1.9 | +2 -4 | 19/21 | 16/25 | 25/31 | 26/31 |
| card_v1c_fewshot, seed 18 | 82.4 | +0.0 | +2 -2 | 19/21 | 16/25 | 27/31 | 27/31 |
| card v1c + retrieve 8 | 79.6 | -1.9 | +3 -5 | 18/21 | 16/25 | 25/31 | 27/31 |
| no card | 0.0 | -81.5 | 0 -88 | 0/21 | 0/25 | 0/31 | 0/31 |
| language tag only (`[python]`) | 0.0 | -81.5 | 0 -88 | 0/21 | 0/25 | 0/31 | 0/31 |
| copy nearest training pair (k-NN) | 10.2 | -- | -- | 7/21 | 2/25 | 2/31 | 0/31 |
| same, excluding the pair's own reference | 3.7 | -- | -- | 0/21 | 2/25 | 2/31 | 0/31 |

- **Examples are worth nothing to an adapter, static or retrieved**: -1.9 / +0.0 / -1.9, all inside
  the ~1-pair e2 seed noise (7a). On untuned models the same context was worth +3.7 to +11.1
  (stage 5). The k-NN control rules out a bad retrieval pool: copying the nearest training pair
  scores 10.2 %, so the examples are relevant but not answers -- the adapter already knows what
  they teach, and re-showing them only perturbs T4.
- **The card is a task trigger, not reference material.** Without it the trained model does not
  write bad selectors; it stops doing the task and reverts to base chat ("Here is a list of every
  `try` block in your code:", "In SQL, the `EXCEPT` clause is used to ..."), and a bare `[python]`
  tag does not substitute. 0.0 % in every tier, against 65.7 % for the adapter TRAINED without a
  card (6b). Two epochs on 820 rows that all carried the card taught "card present -> emit a
  selector" as part of the task.
- **Exec rate is not a quality signal.** Those prose fragments scored 94-95 % "executes": bare
  words like `raise` parse as type selectors. Only `match` means anything when the format breaks.
- So there is no prompt-side headroom to buy at inference on this model, and a real fragility to
  fix: `build_dataset.py --system mixed` varies the prompt per request (card 50 %, `[lang]` tag
  25 %, nothing 25 %) so the request, not the card, triggers the task. That is an arm of the next
  training run; if it holds the 108-pair score, the 700-token card becomes optional at inference.


## Class-form alternatives: the card's vocabulary beside the grammar's (2026-09-15)

Teague prefers `.catch:has(.call)` over `catch_clause:has(.call)`, and wants both: "having
specialized cases is good too". So nothing was retired. `tune/class_alt.py` takes every accepted
training pair whose selector names a grammar type and composes the same shape in the card's class
vocabulary, keeping the original as the candidate's `contrast` so the wording stage is told to
make the difference explicit.

The class is usually WIDER than the type, so these are new questions with their own node sets,
not rewrites: of 281 type-form pairs only 90 have a class form that selects the same nodes
(`.loop` covers for and while, `.class` covers create_table and create_view, `.fn` covers lambdas).
Where the bare class form runs past the 50-node bound the fallback scopes it to the named function
or class the original's nodes sit in (`create_table#organizations column_definition` ->
`.class#organizations .var`), which stays in the card's vocabulary instead of reverting to the type.

Batch classalt1: 61 candidates -> **57 accepted, 4 pending (has-keyword-tokens #133), 0 rejected**,
three wordings each, across 7 languages (cpp 27, sql 13, java 7, bash 4, c 4, python 3, rust 3),
tiers 2/3/4 = 11/27/23. Back-translation of the 4 risky combinator pairs: 12 wordings, 0 read back
as a distractor. They join the next run through `--extra-pairs`, as sfgen's batch did in 7b; the
frozen corpus is untouched. The other 220 type-form pairs get no alternative: the class form is
already a pair (51), its node set is already frozen in training (90), nothing is in bounds (66), or
it is an eval answer (13).

Two defects this batch exposed, both fixed:
- **The wording model echoed the card's class labels across languages**: "the organizations class"
  for a SQL table, "variables inside the users class" for columns, "comprehensions containing a call
  to count" for subqueries. The 96 accepted SQL pairs say table (15), column (18) and subquery (12)
  almost exclusively, and the two that select `.class`/`.comp` at the top level avoid card labels
  entirely ("the named database objects declared here"). WORD_SYSTEM now names the mapping per
  language (SQL .class = table or view, .var = column; C = struct/enum/union; Rust =
  struct/enum/trait/impl; Go = struct/interface; C++ and Java keep "class", their own word).
  Re-wording fixed 12 of 14; two needed a literal comprehension -> subquery substitution.
- **The type-specific original cannot be a distractor when the two forms are equivalent.** Both
  first-round rejections were that: `.class#organizations .var` and `create_table#organizations
  column_definition` select the same 6 nodes, so the distractor matched the reference. Those pairs
  now take both distractors from the relaxations.


### Validating the oracle-first gates against the engine-only path (2026-09-15)

Ten committed batches were re-run through `pilot.oracle_first_verify` on the engine that verified
them, into a copy of `train/pairs`, and compared pair by pair. The first three ran with
`--paraphrases=distinct`; the other seven were re-run a second time with the strict rule they were
actually verified with, because the rule decides which of two pairs with an identical node set
claims it first (cpp-b1 and javascript-b1 each showed such a swap under the wrong rule, and neither
survives the correct one).

| pass | batches | pairs accepted before -> after | gained/lost | references differing | unexplained verdict changes |
|---|---|---|---|---|---|
| distinct rule | audit-r1, prefix-c1, templates-c1 | 224 -> 224 | 0 / 0 | 0 | 0 |
| strict rule | cpp-b2, java-b2, sql-b2, bash-b1, cpp-b1, python-b1, javascript-b1 | 357 -> 357 | 0 / 0 | 0 | 0 |

Every rejection difference is a gate that postdates the batch (the request audit), an id the audit
retired since, or a node set a later batch has claimed -- never the load-bearing or distractor
gates. The vacuous rejections reproduce pair for pair, worded differently ("drop #YAMLReader" vs
"drop to .class .class"), including the ones the oracle answered itself. The verifier self-test's
six hand-checked cases agree on both paths.

Speed, same engine and same batch: audit-r1 16m41s -> 4m57s, prefix-c1 41m52s -> 4m36s. A second
run of an already-verified batch costs seconds, because every reference query is a cache hit --
the class-form batch re-verified in 7 s after a text change.


### Stage 9: the device's new models, and what one model at a time really means (2026-09-15)

The device's store recovered: 33 entries, 19 chat-capable, and seven never scored here -- Ornith-1.0-35B,
Qwen3-Coder-Next, Qwen3.6-35B-A3B and its Turbo, Qwen3.6-27B-Turbo, Qwen3-4B-Instruct-2507, and
**Qwen/Qwen3.5-9B**, which stage 6 recorded as impossible to download. That last one is the tuning base,
so it gives a same-weights device-vs-local reading, and `tiiny ls` shows an existing `Source: Custom`
entry (the uncensored 9B), so custom import demonstrably works on this device.

The first attempt failed twice, and both failures are worth keeping:

- **`--no-embed-pause` is not free.** `qualify.EmbedPause` ssh'es to the embedding host, which is
  `longbottom` -- this machine. Host key verification fails from an unattended session, so every device
  chain has passed `--no-embed-pause`, which disables the protection rather than fixing the hop. `_ssh`
  now runs the command through a local shell when the embed host is this machine.
- **The real contention was two chat models, not the embedder.** Stage 9 loaded Qwen3.5-9B while the
  generation chain's sibling wording stage held gemma-4-26B: `models/running` listed three models
  resident, and the 9B returned three consecutive empty responses (HTTP 200, `finish_reason=None`, no
  content) before qualify's guard skipped the rest. The arm's 80-of-108 result is not a score and is not
  reported as one. `yield_npu` narrows the window between requests but cannot stop another client from
  loading a second model, so the rule is scheduling: device qualification and the generation chain's
  wording stages must not overlap.


### Recovering the suite's "rejected" tier-5 candidates (2026-09-15)

Suite 1 rejected 553 candidates, but only 31 on merit: 522 were engine failures. Two passes and one
harness fix got 277 of them back, and the remaining 246 turned out to be a real engine limit.

| pass | settings | verified | pending | still rejected |
|---|---|---|---|---|
| suite1 (original) | 8 shards, 6 GB each | -- | -- | 522 |
| suite1r | 4 shards, 8 GB each | 60 | 56 | 408 |
| suite1r2 | per-query retry, 16 GB | 101 | 60 | 246 (+1 eval overlap) |

The diagnosis came from running one failing selector by hand: `.call:called-by(kvsprintf)` on the
40-file c-duckhts fixture takes **59 s** when it succeeds and exhausts a **24 GB** memory limit when
it does not ("could not allocate block of size 1.5 GiB"; the recovery unit peaked at 47 GB). The
failures clustered because a CLI process that dies mid-script takes the REST of its shard with it,
and every one of those queries is reported as "no output for query" -- so one explosive selector
rejected dozens of sound pairs. `verify.execute` now retries lost queries one process each
(`ASTCSS_RETRY_LOST=0` disables), which is what the second pass recovered 161 pairs with.

What remains is the engine, not us: 198 process deaths, 45 IO/internal errors and 3 explicit
out-of-memory errors, all call-graph shapes (`:called-by`, `:calls`, `:is-called`) given a whole
process and 16 GB. Worth reporting upstream, and worth knowing before `:in-scope(...)` ships: if it
shares that containment machinery, the tier-5 suite will find its limits too.

Kept after filtering, across the three batches: **4,302 pairs, 2,039 of them tier 5** (kept-suite1
4,025/1,762, kept-suite1r 116/116, kept-suite1r2 161/161). The training corpus today is 1,052 pairs
with no tier 5 at all.


### Recovering the pairs held on #145: `:scope` splits into `:scope` and `:in-scope` (2026-09-15)

sitting_duck main (d706c89) landed two fixes that between them unblock most of what this corpus was
holding: **2a1413d** splits `:scope` (the node IS a scope boundary) from `:in-scope` (the node sits
INSIDE one), and **2a84814** makes a bare type an exact match instead of a prefix (#151). Our 182
pending pairs were written against the documented containment meaning of `:scope(X)`, so they needed
their selector text migrated, not their meaning.

A **second pin** (`workspace/engine/sd-20260915-2001`, main d706c89) exists only to verify pairs held
pending. `sd-20260914-1835` stays authoritative for every score, so no measured number moves.

The oracle needed one correction before it could be trusted against the new build. It walked to the
nearest ancestor in the class set; the engine reads `a.scope.function` / `.class` / `.module`, which
is always a node flagged IS_SCOPE (`node_config.hpp` bit 3). The two differ wherever a class holds
non-scope nodes -- C++ `.fn` covers `function_declarator` (#139) -- so a parameter's nearest `.fn`
ancestor is the declarator while its `scope.function` is the enclosing definition. With IS_SCOPE
required, oracle and engine agree everywhere checked: 3 previously-disagreeing C++ pairs became
1/1, 14/14, 15/15, the `scope`/`in-scope`/`::scope` validation set is 7/7, selftest 343 same 0 differ.

| step | outcome |
|---|---|
| rewrite | 151 pure renames `:scope(X)` -> `:in-scope(X)`; 31 also need the semantic-class argument form, since the grammar cannot split `function_definition#foo` |
| migrate, pre-alignment oracle | 158 accepted, 24 rejected |
| migrate, IS_SCOPE-aligned oracle | **172 accepted, 10 rejected** |
| the 10 | 9 SQL zeros (#166) and 1 honest duplicate of an existing pair |
| SQL re-routed to `create_table#X column_definition` | **9 of 9 accepted** on the new pin |

**181 of 182 recovered.** The 12 C++ pairs that looked ambiguous under the old model (a name in both
a header and a source file) were never ambiguous: `scope.function` attributes each node to its own
enclosing definition. One pair's node set legitimately changed -- `tr-cpp-t5-g030240` froze 10 nodes
under the straddling model and yields 4 now, all inside the `function_definition`; it is accepted
with a wording flag, since its paraphrase says "directly within" while `:in-scope` is any depth.

Two defects found while doing it, both filed:
- **#165** `:has(<semantic class>)` does not match containment: `import_statement:has(.import)` returns
  0 while `.import` matches 297 nodes in the same files. This is the residue after #133's fix and the
  last holdout of the 64 pairs that fix otherwise unblocked (63 of 64 now agree).
- **#166** `:in-scope(.class#name)` returns 0 for SQL: the semantic-class form needs `IS_SCOPE`, which
  `create_table` does not carry, while the bare-type form walks ancestor ranges and works
  (`:in-scope(create_table)` 112, `create_table#projects column_definition` 8, `.class:scope` 0).

Also measured: the oracle's cached class atoms are NOT stale across the two pins -- `.var` 1813,
`.fn` 540, `.call` 1702, `.class` 25 are identical for the oracle cache, the old pin and the new one,
so every comparison above rests on the same class membership.


### The sibling batch, and what the per-query retry was worth (2026-09-15)

Near-miss siblings promoted to pairs of their own: every verified suite-1 pair carries distractors
the oracle already showed select a different node set, so each one that passes the same gates
becomes a candidate. 1,966 candidates from 4,048 source pairs, tier-5 heavy (761 of them).

**1,838 accepted, 120 pending, 8 rejected in 72 minutes** -- T1 3, T2 305, T3 328, T4 558, T5 651,
plus 109 tier-5 and 10 tier-4 held pending on filed defects.

The 8 rejections are the interesting part, because they are all the gates working rather than the
engine failing:

- **7 are eval overlap** -- "continue statements", "classes containing an if statement", "functions
  containing a loop". The generator found the same obvious selectors the eval uses, and the gate
  refused them rather than leaking held-out answers into training.
- **1 is an engine out-of-memory**: `.call:called-by(FormatLogEntry)` (#164).

That last line is the measurement worth keeping. Suite 1, run before the fix, rejected **522**
candidates because a CLI process that died mid-script took the rest of its shard with it. The
sibling batch, run after `verify.execute` began retrying lost queries one process each, lost
**one** -- the query that actually exhausts memory. Same engine, same fixtures, same tier-5 shapes.

Of the 120 pending, **62 are already fixed upstream** and recoverable with the machinery built for
#145 today: 32 has-keyword-tokens (#133), 29 scope-selector (#145), 1 type-prefix (#151). The other
58 are genuinely open: attr-in-has 33 (#150), call-code-literal 22 (#152), chained-receiver 11
(#149), calls-scope 7 (#146), called-by-lambda 3 (#152), exported 1 (#148).


### Recovery roll-up: 230 pairs off the pending list (2026-09-15)

Everything held on a defect that sitting_duck main d706c89 fixes, re-verified against the second pin:

| batch | pairs | what changed |
|---|---|---|
| scope-m1 | 172 | `:scope(X)` -> `:in-scope(X)`, 151 renames and 31 argument rewrites |
| scope-sql1 | 9 | SQL re-routed to `create_table#X column_definition` (#166) |
| sib-recover | 47 | 29 rewritten, 18 simply re-verified (#133, #151) |
| sib-sql | 2 | same SQL re-route, from the sibling batch |
| **total** | **230** | **208 of them tier 5** |

`workspace/recovered.json` is the manifest: batch, path, selector, tier, fixture and node count per
pair, plus how to consume them (`--extra-pairs` on each batch path, skipping those ids wherever the
pending files are read). The originals are deliberately left in place -- the generation chain reads
those pending files for node-set dedupe while it runs.

What is still genuinely pending, after this: the defects that remain open upstream -- attribute
filters inside `:has` (#150), refined call codes (#152), chained receivers (#149), `:calls` scope
(#146), `:exported` (#148) -- plus 12 sibling pairs that carry one of those *alongside* a fixed one,
so the fix alone does not free them.


### The dotted node type is a habit, not an information gap (2026-09-16)

Stage 9's first models miss the SAME five tier-1 pairs, and tier 1 is the easiest tier -- one
semantic class or one node type. Qwen3.5-9B with the card, Qwen3.5-9B with ten examples, and
Qwen3.6-27B-Turbo with the card all fail exactly t1-p20, p21, p22, p23, p25:

| pair | request | reference | what they answer |
|---|---|---|---|
| t1-p20 | every with block | `with_statement` | `.with_statement` (all three) |
| t1-p21 | anonymous functions | `lambda` | `.lambdas`, `.lambda` |
| t1-p22 | definitions that carry decorators | `decorated_definition` | `.decorated_definition` (all three) |
| t1-p23 | continue statements | `continue_statement` | `.jump#continue`, `.continue`, `.continue_statement` |
| t1-p25 | while loops | `while_statement` | `.loop#while`, `.while`, `.loop` |

Every miss is the same move: take a node type and dot it, or invent a class-plus-name filter
(`.jump#continue`, `.loop#while`) rather than write the bare type.

**It is not missing information, and it is not immovable either.** card_v1c lists `with_statement`,
`while_statement`, `continue_statement`, `decorated_definition` and `lambda` by name, under a heading
that says "PYTHON NODE TYPES (exact tree-sitter names, when no class fits)". card_v1c_fewshot adds
two worked examples of the shape (`every assert statement -> assert_statement`, `every ternary
conditional expression -> conditional_expression`).

Those two examples fix the error -- for a model strong enough to generalise from them. The
27B-Turbo's few-shot arm answers `with_statement`, `lambda`, `decorated_definition` and
`continue_statement` bare and correct, taking tier 1 from 16/21 to **20/21** and the arm from 87.0 to
**92.6**. The 9B read the same two examples and changed nothing: still `.with_statement`,
`.lambdas`, `.decorated_definition`.

| pair | 9B card | 9B few | 27BT card | 27BT few |
|---|---|---|---|---|
| t1-p20 | `.with_statement` | `.with_statement` | `.with_statement` | `with_statement` OK |
| t1-p21 | `.lambdas` | `.lambdas` | `.lambda` | `lambda` OK |
| t1-p22 | `.decorated_definition` | `.decorated_definition` | `.decorated_definition` | `decorated_definition` OK |
| t1-p23 | `.jump#continue` | `.continue_statement` | `.continue` | `continue_statement` OK |
| t1-p25 | `.loop#while` | `.loop` | `.while` | `.while` |

So the dotted type is a capability-dependent habit: two positive examples are enough for a 27B and
not enough for a 9B, and a vocabulary list alone is enough for neither. It is worth ~4.6 points where
it persists, which makes it the largest error class left in the prompt-side results for the smaller
models.

t1-p25 is the residue: every arm, including the one that learned the lesson, invents `.while` or
`.loop` for "while loops" -- `.loop` exists as a class, so `while` reads as a modifier of it rather
than as part of a type name. An explicit negative line ("write `with_statement`, never
`.with_statement`") is a HYPOTHESIS for the models the examples do not reach, not a change to make:
stages 2-4 showed every added prose rule hurt the models that did well without it (card v2's type
rules cost gemma 18 regressions). Test it as an arm, per model, the way the card arms were tested.


## From stage 9 (seven new device models, plain / card / few-shot, 2026-09-16)

The device's model store recovered, so seven chat models that had never been scored became
available -- including `Qwen/Qwen3.5-9B`, which stage 6 recorded as impossible to download and which
is the base we fine-tune. Three arms each, the stage 5/6 arms so the numbers join that table:
**plain** (no system message at all), **card** (card_v1c.md), **few** (card_v1c_fewshot.md, v1c plus
ten examples).

| model | plain | card | few-shot | few - card | s/answer | tokens |
|---|---|---|---|---|---|---|
| Qwen3.6-27B-Turbo | 0.0 | 87.0 | **92.6** | +5.6 | 1.88 | 6 |
| Ornith-1.0-35B | 0.0 | 84.8 * | 91.6 * | +6.8 | 6.78 | 283 |
| Qwen3-Coder-Next | 0.0 | 81.5 | 84.3 | +2.8 | 0.86 | 6 |
| Qwen3.6-35B-A3B | 0.0 | 77.8 | 83.3 | +5.6 | 0.84 | 6 |
| Qwen3.6-35B-A3B-Turbo | 0.0 | 76.9 | 80.6 | +3.7 | 0.89 | 7 |
| Qwen3.5-9B | 0.0 * | 69.4 | 73.1 | +3.7 | 0.89 | 5 |
| Qwen3-4B-Instruct-2507 | 0.0 | 49.1 | 64.8 | **+15.7** | 0.49 | 6 |

\* Ornith card 105 and few 107 answered (empty responses); the 9B's plain arm 107 (stopped by the
contention guard). Every other arm answered all 108.

- **The floor is zero, unanimously.** Seven models from 4B to 35B -- general, coder and reasoning --
  score **0.0 % with no card**, in every tier. They do not write wrong selectors; they answer the
  request as a chat turn: "Here are the most effective ways to find...", "Could you clarify what you
  mean by...", "Since you didn't specify a language or context...". A coder-specialised model is no
  exception, which is the strongest evidence yet that the card supplies genuinely novel vocabulary
  rather than cueing something the models already half-know.
- **Plain arms are expensive as well as useless**: 189-1513 mean completion tokens against 5-7 with a
  card, and up to 113 minutes per arm (Ornith) against ~2 minutes. Exec rate is meaningless there --
  it ranged from 46 % to 100 % across the plain arms while match stayed at 0 -- because prose
  fragments parse as type selectors.
- **Few-shot beats the card for every model measured, without exception**, +2.8 to +15.7. The gain is
  largest where the model is weakest (4B +15.7), matching stage 5: examples fix structure, and the
  models with the most structural errors have the most to gain.
- **Active parameters matter more than total.** The 35B-A3B pair (~3B active) sits at 77-83 while the
  27B-Turbo reaches 87-93. Turbo variants are a latency choice, not a quality one, except for the 27B
  where Turbo is the one we measured highest.
- **Ornith is the accuracy/latency trade in one row**: second best at 91.6, at 6.8 s and 283 tokens
  per answer -- roughly seven times the 27B-Turbo's latency for 1 point less.
- Device-vs-local, same weights, same card: **Qwen3.5-9B scores 69.4 on the device against 64.8
  locally under NF4**, the first time we could measure that gap, since the 9B could not previously be
  downloaded to the device.


### Deployment: our half works, the device's import toolkit is down (2026-09-16)

The first tuned model is published: **https://huggingface.co/teaguesterling/qwen3.5-0.8b-astcss**
(Qwen3.5-0.8B + the seed-18 LoRA, merged, 752,393,024 F16 parameters, 1.5 GB, public).

Getting there caught a bug worth remembering. **The first merge applied nothing and said so only in a
UserWarning.** `train_qlora.py` loads the base with `AutoModelForCausalLM`, so every adapter key is
`base_model.model.model.layers.<n>...`; `merge_adapter.py` tried `AutoModelForImageTextToText` first,
which puts the text stack at `model.language_model.layers.<n>`. PEFT matched none of the 372 adapter
tensors, `merge_and_unload()` returned the base unchanged, and the output looked plausible -- 1.7 GB
of safetensors with the right architecture string. Max|delta| against the base was 2.98e-08 on every
tensor, including `embed_tokens`, which the adapter never touches. One step from publishing a base
model labelled as a tuned one.

`merge_adapter.py` now loads the base the way training did and `verify_merge()` EXITS if the targeted
modules are indistinguishable from the base. The corrected merge reports 186 targeted tensors at
max|delta| 4.6e-3 against 4.9e-4 for untouched ones -- and that 4.9e-4 is itself one fp16 ulp at
norm-weight magnitudes, not a modification. The merged weights then re-scored at **82.4 %**: T1 19/21,
T2 17/25, T3 25/31, T4 28/31, identical to the adapter tier for tier.

The device will not take it yet:

```
tiiny import https://huggingface.co/teaguesterling/qwen3.5-0.8b-astcss
  -> not supported: Toolkit catalog is unavailable. (TOOLKIT_CATALOG_UNAVAILABLE)
tiiny import https://huggingface.co/Qwen/Qwen3.5-0.8B          # control
  -> not supported: Toolkit catalog is unavailable. (TOOLKIT_CATALOG_UNAVAILABLE)
```

**The control is the point**: Qwen's own official repo fails identically, so this is a device-side
outage in the import toolkit, not a rejection of our model, its size, or its text-only
`Qwen3_5ForCausalLM` layout. The store catalog is healthy the whole time (33 entries, management API
responding, models load and serve). Stage 6 recorded the same subsystem reporting `invalid`.

So the open question -- whether custom import accepts anything other than a 9B-shaped multimodal
model, which is the only custom entry on that device -- stays open, and re-shaping the upload to match
that layout would be solving a problem the control says we do not have. Retry the import when the
toolkit recovers; everything on our side is done.

Note for whoever picks this up: the merged build is text-only. `save_pretrained` under the CausalLM
class drops the base's vision tower (153 `model.visual.*`) and multi-token-prediction head (15
`mtp.*`). That is recorded in the model card.


## A mutator tier (proposal, 2026-09-16)

Scoped but not started: `docs/mutator-tier.md` — jQuery-style mutations (`rename`, `wrap`, `insertAfter`
...) as a new tier on this same execution-verified frame. Three things found while scoping it that are
facts rather than proposal, so they belong here too:

- pluckit already implements **14 mutation ops** with a documented chain grammar and a sound safety
  gate, and all 14 lower onto just **four** `ast_patch` edit kinds. The API was not the blocker it
  looked like.
- sitting_duck `feat/ast-patch` (100b9e1) has `ast_patch`/`ast_replace`: byte-exact and pure, returning
  patched text without writing. This makes a *second* oracle available for mutations, so the
  oracle-first split that reproduced 581/581 selector verdicts carries over directly.
- **In-place mutation would void the result cache.** `_fixture_key()` hashes fixture files by
  `st.st_mtime_ns`; `MutationEngine` writes and restores content but not mtime. Anything that verifies
  through pluckit rather than `ast_patch` silently discards the 16m41s -> 4m57s cache win, and cannot
  shard (its rollback is best-effort against a shared fixture tree).

Unbuilt and deliberately so: the cheapest test is 20-30 hand-built pairs through the stage-9 harness to
find whether these models emit a well-formed chain at all, before any corpus exists.

## Which output surface can a small model write? And should one model write it all? (2026-09-16)

`surface/` — 6 surfaces x 20 mutations x 3 device models x 2 prompt conditions = 720 rows
(`workspace/surface/rows-full2.jsonl`). Same fixture, same selector vocabulary, same operation
table in every arm; only the wrapper syntax differs, so a gap between arms is the surface's doing.
Surfaces: A jQuery chain, B pluckit argv, C JSON, D PSS (`{ op: rename; to: x; }`), E prefix call,
F PSS shorthand (`{ rename: x; }`). Selectors scored BY EXECUTION, not string equality.

**Two harness bugs fabricated a result before any of this was trustworthy.** Both were found by
reading raw model text after a 3-task smoke run, and either alone would have produced a confident
and wrong ranking:
  - the shared operation table wrote arity as a bracketed token (`remove [0]`), and Qwen3-4B
    transcribed the annotation into its answers in four of five surfaces (`.remove[0]`,
    `"args": [0]`). PSS was spared only because `{ op: remove; }` has nowhere to append it.
    Stating arity in prose: A 0/3 -> 2/3 correct, E 0/3 -> 3/3, D unchanged. D's entire apparent
    lead was one token in a card shared by every arm.
  - the scorer tallied the arity-0 denominator after the `continue` for unparsed rows, so a
    surface failing every arity-0 task reported 0/0 rather than 0/6.
A third defect was a parity failure: D and F NAME their arguments while A/B/C/E position theirs,
and the card only instantiated the key names its two examples happened to use, so the model
generalised `to:` to addParam/addArg. Five of D's fourteen failures were that gap; D was being
scored against a vocabulary the card never gave it. The key list is now GENERATED from
PSS_ARGKEYS so the card cannot drift from the parser.

**Result (card condition, fully correct / 20).**

| model | A jq | B argv | C json | D pss | E prefix | F short |
|---|---|---|---|---|---|---|
| Qwen3-4B-Instruct-2507 | 13 | 17 | 17 | 10 | 13 | 12 |
| Qwen3-8B               |  8 | 11 |  9 |  3 | 12 |  7 |
| Qwen3.5-9B             | 17 | 17 | 18 | 10 | 16 |  9 |

D and F are bottom-two on all three models. D's gap persists on the STRONGEST model (10/20 against
17-18 for A/B/C), so it is not a small-model artifact that scale washes out. F is NOT monotone --
9/20 on the 9B but 12/20 on the 4B -- so only D's penalty holds across the whole ladder.

**Where the difference lives: the selector, and only the selector.** On the 9B card arm, `op` is
18-20/20 and `args` 16-20/20 on every surface; `selector` is 17-18 for positional surfaces and 11
for both keyed ones. Every discriminating task has the signature `sel=False, op=True, args=True` --
the model knows what to do and what to do it with, and aims at the wrong nodes. This rules out
argument-keying as the cause: D and F key arguments quite differently yet both lose only the
selector column. The shared property is that the selector heads a CSS rule. B_argv's selector is bare and unquoted
too and is fine, which argues against quoting or bareness -- but that is ONE discriminating surface,
and E_prefix quotes its selector and sits mid-pack while C_json quotes and leads. So the claim stays
at "the rule form, not argument keying"; blaming the `{` specifically is not supported by a single
comparison, least of all with the card-example confound below in play.
The keyed surfaces add a `.mod`/`.class` ancestor step the reference lacks 3-5x more often, on all
three models. Caveat: many of those are `.class#User`, copied from card_v1c's own example (`User`
is not even a class in the fixture), so the data cannot separate "CSS framing invites CSS-idiomatic
qualification" from "the PSS arms are likelier to copy the card's example". A card whose example
carries no combinator would settle it. A related hypothesis DIED: D and F do not agree with each
other more than other surface pairs do (D==F 16/20, 8/19, 19/20 vs baseline B==C 16/20, 10/19, 18/20).

**A design bug in PSS worth fixing regardless of any of this.** A valueless declaration
(`{ remove; }`) is silently dropped, leaving a bare selector -- and a bare selector means
`show: body`. The mutation silently becomes a view: no error, wrong action. In the few-shot
condition, where the `remove: true` convention is never demonstrated, BOTH models wrote exactly
that form on exactly the 6 arity-0 tasks (6/6 on each, 0 malformed under the card). The most
natural thing a model writes in the shorthand is the one form PSS misreads as a read.

**Two models beat one surface.** Since op+args is 85-100% everywhere and only the selector
collapses, the obvious split is a selector specialist plus a general model for op+args. Feeding the
tuned 0.8B (`workspace/merged/qwen3.5-0.8b-astcss`, the 82.4% model) the whole mutation request
scores 55% -- but 7/20 of those are the RIGHT target with an argument-derived qualifier bolted on
(`.fn#get_user:has(.call#verbose)`), which is off-distribution prompting, not targeting error. Given
the targeting clause a pipeline would actually hand it ("the get_user method"), it scores **18/20**.

Composing per task (both halves right on the SAME task, not a product of marginals):

| arm | op&args | composed | that model alone |
|---|---|---|---|
| 8B card D_pss | 90% | **85%** | 15% |
| 8B card B_argv | 90% | 85% | 55% |
| 9B card C_json | 100% | 90% | 90% |
| 4B card B_argv | 95% | 85% | 85% |

The split does NOT beat the best single model (90% either way). What it does is make end-to-end
accuracy independent of the op-model's selector ability: weak arms lift to 75-85% and the PSS penalty
disappears (D_pss 15-50% -> 75-85%). It adds nothing only where the op-model's OWN selector accuracy
already exceeds the specialist's -- `9B card C_json` (90% -> 90%) is the clean instance of that.
`4B card B_argv` is not: at 85% composed against 95% op&args and the specialist's 90%, it is bounded
by which TASKS the two halves fail on, not by either marginal, so it should not be read as "the split
adds nothing for the 4B". So under a two-model split, PSS can be chosen on ergonomics rather than
ruled out on accuracy.

**Limits.** 20 tasks whose selectors are easy (14/20 single-step `.fn#name`), so the 0.8B's 18/20
is not comparable to its 82.4% on the real eval. The targeting phrases were hand-written, so the
op-extractor that would produce them is unmeasured and is a real component of a deployed pipeline.
Bigger still: those phrases are in EXACTLY the register the 0.8B was trained on (English -> selector),
while the device models were handed mutation requests. So 18/20 is a best-case, matched-register
number, and the 55% -> 90% gap conflates off-distribution prompting (real) with the specialist being
evaluated on its own training distribution while the generalists were not. The composition
measurement does not rest on this; the 90% headline does.
The op+args halves are reused from answers where the model also produced a selector; a dedicated
op-only prompt could score differently either way. Prompt condition interacts with both model and
surface and did not resolve: examples help D consistently (4x across runs) and help the older 8B,
while a written syntax description wins for the newer instruct-tuned 4B.

### The two-model pipeline, measured end to end (2026-09-16)

The 18/20 selector figure above used targeting phrases I wrote by hand. Measuring the extractor
instead (device model splits the raw request into {target, op, args}; the extracted target goes to
the tuned 0.8B; all three parts scored together) changes the picture twice.

The op model needs NO selector vocabulary -- only the operation table -- which is why this half
could be much smaller than a model that has to emit a selector itself. Both models produced valid
JSON 20/20 at the first attempt.

| | sel | op | args | end-to-end |
|---|---|---|---|---|
| v1 4B + 0.8B | 11/20 | 20/20 | 15/20 | 35% |
| v1 9B + 0.8B | 14/20 | 20/20 | 17/20 | 65% |
| v2 4B + 0.8B | 17/20 | 20/20 | 17/20 | 70% |
| v2 9B + 0.8B | 17/20 | 20/20 | 18/20 | 75% |
| hand-written targets | 18/20 | - | - | (86% estimated) |
| those models ALONE | - | - | - | 85% / 90% |

v1 -> v2 changed only the extraction instruction: "target is a NOUN PHRASE, verb removed", plus two
examples. The 4B had been copying the whole request into `target` ("delete the search_users
method"), which handed the 0.8B a mutation request and reproduced the argument-leakage failure
exactly. So the extractor deficit was mostly a prompt bug -- but op EXTRACTION being free (20/20)
does not make TARGET extraction free, and my earlier estimate was optimistic because I supplied the
best-case input myself.

**The split still loses to one model on this set**, because errors compound across stages: 17/20
selectors and 17/20 args compose to 14/20, since different tasks fail in each half. The split's
benefit is confined to rescuing a model that is bad at selectors (8B/D_pss 15% -> 85%); where the
single model is already strong at selectors, the extra stage only adds failure modes.

**The tuned ladder (same 108-pair eval, langcard-e2) argues for one tuned 4B, not a 9B and not a split:**

| tuned | exec_match |
|---|---|
| 0.8B fp16 | 81.5% (merged 82.4%) |
| 2B fp16 | 82.4% |
| **4B nf4** | **89.8%** |
| 9B nf4 | 77.8% |

2B buys nothing over 0.8B (+0.9), so a 2B selector model is not worth its cost; 4B is the sweet spot
(+7.4); the 9B is WORSE than the 0.8B (4B and 9B were both NF4, so quantisation is not the
explanation, though the 9B runs differ in data fraction and epochs -- hold that one loosely). Every
size scores 0.0% with no card, at every scale.

**A measured reason to train one model on BOTH selectors and mutators:** a selector-only model
degrades sharply when the request contains the mutation. The 0.8B scores 18/20 on targeting phrases
and 11/20 on the same targets phrased as mutations, folding the argument into the selector
(`.fn#get_user:has(.call#verbose)`). Training on mutators removes exactly that failure, so "trained
on both" fixes a measured degradation rather than being a convenience.

### A tuned 4B as the single executor, and why "trained on both" is not optional (2026-09-16)

Teague's framing: the large model decides WHAT to change and says "add the n parameter to foo and
add this if statement"; the small model turns that into an executable mutation. So the small
model's job is instruction -> mutation, which is exactly what the 20 tasks measure.

Tested `ladder-qwen3.5-4b-nf4-langcard/epoch2` (the 89.8% adapter) as that executor:

| | tuned 4B | tuned 0.8B |
|---|---|---|
| raw mutation request -> selector | 13/20 | 11/20 |
| extracted target phrase -> selector | 18/20 | 17/20 |
| composed with the 9B's op/args | 16/20 = 80% | 15/20 = 75% |

**A selector-tuned model leaks the mutation into the selector, and it is not a small-model
artifact.** At 4B the same failure appears: `.fn#execute .call#del` for "REMOVE the params
parameter", `.class#SearchUsers .call#replace`, `.fn#load .jump`, `.fn#connect .call#create_connect`.
Handing it a clean targeting phrase recovers 5/20. So training one model on selectors AND mutators
is not a convenience -- it repairs a measured 25% degradation that survives a 5x parameter increase.

Qualifications: the tuned 4B beats the tuned 0.8B only 18 vs 17 here, because these selectors are
too easy to expose the ladder's real gap (89.8% vs 82.4% on the 108-pair eval) -- this task set
ceilings. And composed 80% still trails a single untuned 9B end-to-end (90%), so on THIS set the
split does not win; its value remains rescuing models that are weak at selectors.

### Mining "what to edit to" from git history: what works today (2026-09-16)

The hard half of a mutator corpus is not the selector, it is the replacement content. Git history is
the natural source of real before/after pairs. Status of the machinery, checked rather than assumed:

  * `parse_ast(<source string>, <language>)` parses inline content in our pinned engine (verified:
    16 nodes, 1 function_definition, 0 errors). So content fetched from git can be parsed directly.
  * `read_ast` DOES understand `git://` URIs, but only by PASS-THROUGH: `ast_file_utils` detects a
    URI scheme and hands the path to DuckDB's virtual filesystem "without local fs checks"
    (src/ast_file_utils.cpp:188). It does not implement git itself. The git VFS is registered by
    duck_tails -- which is exactly the extension we cannot load alongside it (see the ABI note
    below). So `git://` reads are unavailable to us in practice, for a different reason than
    "unsupported". (An earlier draft of this section claimed git:// appears nowhere in the source;
    that was a grep against a path that does not exist, and was wrong.)
  * duck_tails provides the git table functions (`git_tree`, `git_read`, `git_uri`, `read_git_diff`,
    `git_log`); fledgling's `repo.sql` only wraps them, and `file_changes` is written as a
    blob-hash join between two `git_tree` scans -- which WOULD make enumerating changed files a
    query rather than a subprocess per file. UNVERIFIED: that is source reading. Live, `git_tree`
    returned 1 row on a freshly created single-commit control repo but 0 rows on every real repo
    tried, in both the `(repo, ref)` and `git://repo@ref` forms. The mining primitive is therefore
    plausible but has not been demonstrated, and the discrepancy is unexplained. Anyone building on
    this should confirm it with the duck_tails author before assuming it scales.
  * BLOCKER: duck_tails is built for DuckDB `b155d6f63c` and our sitting_duck CLI is `d8cdaa33fd`,
    so the two extensions cannot load in one process. Mining must therefore be a two-process batch
    (duck_tails extracts content pairs -> parquet -> sitting_duck parses), or one side gets rebuilt.

**Op labels do not come free.** `structural_diff`'s entire vocabulary is `added` / `removed` /
`modified` at (name, semantic_type) granularity, with change detected via descendant_count and
children_count. It says THAT `foo` changed, never that a parameter was added or a call was wrapped.
Mapping a real diff onto the 14 mutator ops is unwritten and is the tier's main engineering cost.

**And the argument is only recoverable for some ops.** For mechanical ops (rename, addParam,
removeParam, addArg, removeArg, remove, unwrap) the diff determines the argument exactly, so those
pairs can be mined and execution-verified. For content ops (append, prepend, wrap, replaceWith,
insertBefore/After) the argument is code a human authored; mining them teaches transcription, not
judgement. Under Teague's architecture that gap closes, because the large model supplies the content
and the small model only has to place it -- so the corpus needs to teach placement and form, which
IS minable, with the request back-translated from the diff by the existing wording model.

## Stage 10 arm 1: the tier-5 corpus (6,053 pairs), and why one eval hid the result (2026-09-16)

Qwen3.5-0.8B, per-language card, cap 8, 2 epochs, seed 18. 6,053 pairs / 15,928 rows / 2,599
selector shapes, against the 820 / 2,205 / 297 of the corpus behind the 82.4% baseline.
Val loss 0.0833 (e1) -> 0.0557 (e2). Adapter: `workspace/adapters/t5-langcard/epoch{1,2}`.

| | 108-pair eval | eval_t5 (55) |
|---|---|---|
| epoch 1 | 82.4% | **83.6%** |
| epoch 2 | 82.4% | 80.0% |
| baseline (820-pair corpus) | 82.4% | 34.5% |

**The 108-pair eval is saturated for this model size and hid the entire result.** Three different
training configurations land on exactly 89/108 = 82.4%: the old baseline, t5 epoch 1 and t5 epoch 2.
Only the tier distribution moves (baseline 19/17/25/28, e1 17/20/28/24, e2 17/19/27/26). Reading
that eval alone, the 7.4x corpus scale-up bought nothing.

**On the eval the corpus was built for it bought +49 points.** Same model size, same card, only the
corpus differs: `stage7c-t5-qwen3.5-0.8b-langcard-e2` 34.5% -> `stage10-t5-t5-langcard-e1` 83.6%.
For scale, on that same eval a 4B trained on the OLD corpus scores 67.3% and an untuned 9B 60.0% --
so a 0.8B on tier-5 beats a 4B on the old corpus. That is a claim about corpora, not architectures:
neither the 4B nor the 9B has been trained on tier-5, and doing so is the obvious next experiment.

**Epoch 2 is the worse checkpoint despite the better val loss** (0.0557 vs 0.0833): 83.6% -> 80.0%
on eval_t5, identical on the 108. Two pairs out of 55 is within noise, but val loss is clearly not
tracking eval here, and epoch 1 is what should be carried forward.

Method note for anyone reading these numbers: the epoch-2 val loss is NOT comparable to the
baseline's 0.3548 -- different and larger validation set (733 pairs). Only the e1->e2 movement
within this run is meaningful.

Arm 2 (`t5-mixed`, `--system mixed`, aimed at the 0.0%-without-a-card cliff) was queued behind
arm 1 and has NOT run; the unit exited after arm 1's scoring.

### The tier-5 adapter as the selector half: better AND more brittle (2026-09-16)

`workspace/adapters/t5-langcard/epoch1` (the checkpoint that scores 83.6% on eval_t5) run over the
20 mutation tasks, exactly as the merged 82.4% model and the tuned 4B were:

| | raw mutation request | extracted target | composed with the 9B's op/args |
|---|---|---|---|
| merged 0.8B (82.4%) | 11/20 | 17/20 | 15/20 = 75% |
| tuned 4B (89.8%) | 13/20 | 18/20 | 16/20 = 80% |
| **tier-5 0.8B (e1)** | **9/20** | **19/20** | **17/20 = 85%** |

**Best selector half measured here, and the worst leakage.** On a clean targeting phrase it is the
strongest of the three -- 19/20, beating a 4B five times its size. Handed the raw mutation request
it is the weakest -- 9/20, below the model it replaces. The clean-vs-raw gap widens monotonically
with specialisation: -6 (merged), -5 (tuned 4B), -10 (tier-5).

The failures explain the direction. The tier-5 model is more FLUENT in astcss, so mutation words in
the request get spent on more elaborate wrong selectors built from that fluency:
`.fn#search_users ~ safe_search`, `.fn#get_user .fn[params=False]`,
`.fn#execute .fn:not(:has(.fn#p...))`, `.fn#main .fn#setup_logging`, `.fn#load .fn#insert_validate`,
`.fn#close .call#None`, `.fn#connect .var#ready`. Combinators, attribute filters and :not(:has())
are all tier-5 vocabulary. A weaker model simply echoes the name; a stronger one constructs a
grammatical answer to the wrong question.

So **selector-only specialisation makes off-distribution mutation phrasing WORSE, not better**, and
training one model on selectors AND mutators is the fix for a problem that grows as the selector
half improves.

**This also revises an earlier conclusion in this file.** With the tier-5 selector the composed
pipeline reaches 85% -- tying a single untuned 4B and trailing only the 9B (90%) -- so "the split
still loses to one model" is no longer accurate on this task set. Caveat on cost: that 85% pairs a
0.8B selector with the 9B as EXTRACTOR. The 4B-extractor pipeline measured 70% with the older
selector and has not been re-run with this one, so a cheap "0.8B + small extractor" remains
undemonstrated.

### Growing eval_t5: why the cheap pool does not work (2026-09-16)

eval_t5 is 55 pairs (42 accepted + 13 pending; rejected excluded), which is a thin instrument --
the epoch-1-vs-epoch-2 difference in stage 10 was 2 pairs. The obvious way to grow it is the 1,221
corpus pairs that did not make it into the training set. That does not work, and the reason
generalises.

Those 1,221 are exactly `dropped_by_template_cap` from the dataset manifest: they were excluded
BECAUSE their selector template had already been used 8 times. Measured against the 6,053 trained
pairs:

| | count |
|---|---|
| unused pool pairs | 1,221 |
| novel css **string** | 1,165 |
| novel css **template** (names stripped) | **0** |

Every one of the 1,165 is same-shape/new-name. The commonest shapes are `.call[receiver="V"]` (285),
`.var#N` (103), `.fn#N::callees` (93). An eval built from them would measure name substitution
against shapes the model saw up to 8 times, and would score deceptively high.

**The lesson is about the gate, not the pool.** `pilot.eval_overlap` matches on exact normalised
`nl`/paraphrase text and exact `css` string. All 1,165 pass it. The gate is necessary and not
sufficient: held-out-ness has to be judged by selector SHAPE, not by string identity, or an eval can
be "disjoint" from training and still test nothing new.

**A second constraint, easy to trip over:** eval_overlap is applied when a DATASET IS BUILT, not
continuously. `t5-langcard` was built 2026-09-16 08:33 against the eval as it then stood, and stage
11 (the 4B) is training on it now. Adding pairs to `eval_t5/pairs/` afterwards does not retroactively
remove them from that dataset -- so any grown eval must be checked absent from the built dataset's
own pairs, or it silently contaminates every model already trained on it.

**What the real pool is:** `eval_t5/candidates/selectors.jsonl` holds 126 drafted selectors, 38 of
which became eval pairs, leaving 88 unused. They carry `css`/`struct`/`distractors`/`family` but no
`nl`. Per draft_t5.py the eval's standard is HAND-WRITTEN wordings, under a strict rule (no two of
request and paraphrases sharing more than half their content words). So growing 55 -> ~143 is an
authoring task, not an automation one; using the wording model instead is possible but would weaken
exactly the property that makes the eval worth trusting.

## Does a real edit decompose into standalone operations? (2026-09-16)

4,823 real edits mined from Claude Code transcripts (33 local + 1,609 on snape) via
`editmine/extract_edits.py`: Edit/Write tool calls carry {file_path, old_string, new_string},
a before/after pair at a known path. 2,598 are in code files.

Coarse ops: replace 63%, append 16%, prepend 9%, signature_edit 6%, rename_token 5%,
**wrap 0.3% (16 of 4,823)**, delete 0.06%. Two of the operations one would naturally put in a
mutation API are near-absent in practice.

**`replace` mostly does NOT decompose.** Sub-classifying the 1,785 code replaces
(`editmine/subclass2.py`, composition-aware, multi-label):

| | share |
|---|---|
| carries a non-comment named op | **26.7%** |
| comment_added only | 46.4% |
| unexplained rewrite | 26.6% |

A first pass reported 73.4% "explained", which was wrong: `comment_added` fires whenever any
added logical line is a comment, and with median churn of 11 lines most large rewrites trip it
incidentally. The comment-only records are +17/-4, +25/-2, +35/-4 rewrites that happen to contain
comments -- not comment-addition operations. Named ops that do stand alone, as a share of replace:
wrap_expression 7.3, literal_changed 6.8, condition_changed 4.5, import_added 3.2, try_wrap 3.1,
addArg 2.4, addParam 1.9, return_changed 1.8, removeParam 0.6, removeArg 0.4.

**`append` decomposes well** (261 code records): call_statement 35%, function/class 22%,
statement 12%, branch 10%, import 7%, doc/comment 6%, assertion 3%, return 2%, logging 2%.
"Append a call / a branch / an import / an assertion" are real operations with real frequency.

**Composition is real but shallow:** 275 records carry two labels, 47 three, 11 four. The
commonest pair is comment_added + wrap_expression. A mutation API wants to apply a couple of ops
per call, not long chains.

**Method note that matters more than the counts:** wrap_expression, addArg and addParam only
became visible after joining physical lines by paren depth -- `const Opts &o)` ->
`&o,\n const string &fmt)` reads as an unclassifiable rewrite line-by-line and as addParam once
joined. LINE-BASED DIFFING SYSTEMATICALLY HIDES THESE OPERATIONS. Mining the vocabulary properly
wants AST diffing of both revisions, which sitting_duck can already do (parse_ast takes inline
source, verified). `move` is worse than hidden: it appears as a delete in one Edit and an insert
in another, so no per-record classifier can see it -- only 2 in-record reorders were found.

**Per-language differences are mild:** replace dominates everywhere (60-73%); only the secondary
op shifts (.hpp append 21%, .mjs prepend 15%, .rs prepend 13%, .sql signature_edit 11%). That is
an argument against separate per-language mutation vocabularies -- same ops, different mix.

**Intent, honestly:** usable per-edit labels are 64 (43 local + 21 snape), taken from the THINKING
block preceding a call ("use the stored p['split'] instead of recomputing it with the old hash" ->
exactly that edit). Turn-level prose adjacent to a call is status narration and must not be used.
A symbol-overlap salvage of shared thinking measured 30% and did not survive reading the text.
Bash `description` (308 local, agent-written, per call) is the other genuine intent source.
The scalable path stays back-translation from the diff, as with the selector corpus.

### AST diffing finds what line diffing cannot (2026-09-16)

Teague: "Isn't this exactly what sitting_duck can do with parse_ast from json?" Yes in principle,
with one correction and one caveat.

**Correction, itself corrected (2026-09-16).** `parse_ast` proper does not accept a column --
"Table function parse_ast does not support lateral join column parameters" -- and I concluded from
that one probe that the whole approach needed a temp-file workaround. WRONG: the column-accepting
variants already exist beside it in the same build, under different names.

  parse_ast_list(code, lang)        scalar     -> LIST of nodes per row
  parse_ast_list_table(code, lang)  table_macro-> full AST rows, LATERAL-compatible

Verified against the real harvest AND against the pinned scoring engine sd-20260914-1835 (which has
both, so mining and verification need no build split):

    SELECT t.type, count(*) FROM read_json_auto('edits-*.jsonl') e,
           LATERAL parse_ast_list_table(e.old, e.lang) t GROUP BY 1;

300 edits parsed with a per-row language column. So the AST-diff miner IS one query, and the
per-fragment temp-file route was unnecessary work built on an incomplete probe.

**Caveat: fragments parse well except SQL.** Clean-parse rate over 300 sampled old-fragments:
bash 88.9%, python 73.0%, javascript 72.7%, rust 68.8%, cpp 68.0%, **sql 18.2% (4.2 errors/frag)**.
SQL here is DuckDB macro bodies and partial statements; it needs file context, not fragments.

**The demonstration.** 60 pairs that the line-based classifier could only call `rewrite`, re-diffed
by node-type counts from read_ast:

  now carry >=1 named op: 39 / 60 = 65%
  +addArg 26, +wrap/addCall 25, +addComment 7, +condition_changed 3, +return_changed 3,
  +addParam 3, and the corresponding removals.

Exactly the operations predicted to be hidden: argument/parameter changes that wrap across line
breaks, and expression-level wrapping. So the earlier "26.7% of replace decomposes" is a floor set
by the METHOD, not a property of the edits -- with AST diffing a large part of the `rewrite`
residue is nameable after all.

Still out of reach per-record: `move`, which spans two separate Edit calls and needs cross-edit
correlation within a session regardless of diff method.

### The operation vocabulary, mined by AST diff (2026-09-16)

`editmine/astdiff.sql`, one query, 2,184 mined edits with a mapped language. Node-type deltas
between the parsed old and new fragments; an asymmetric delta is an operation performed.

| op | added in | removed in |
|---|---|---|
| comment | 1140 | 53 |
| arg | 1083 | 122 |
| call/wrap | 1081 | 125 |
| condition | 641 | 83 |
| return | 629 | 57 |
| param | 435 | 36 |
| function | 430 | 43 |
| error_handling | 137 | 14 |
| import | 125 | 7 |

**Coverage: 1,720 / 2,184 = 79% carry a named op, against 26.7% by line diffing.** The earlier
number measured the method, not the edits -- confirming the 60-pair probe. param and arg are the
clearest case: 435 and 1,083 here versus 34 and 43 found by line diffing, because both wrap across
line breaks and line-based detection cannot see them.

Three caveats, so this is not mistaken for a finished vocabulary:
  * `comment` leading at 1,140 repeats the earlier trap one level up -- a node-type delta fires on
    ANY change in comment count, so a large rewrite touching a comment is counted. Needs the same
    pure-vs-incidental split that cut line-based comment_added from 64% to a true 1.6%.
  * `arg` and `call/wrap` at ~1,080 each are near-certainly correlated: adding an argument changes
    argument_list AND its enclosing call_expression. Probably one operation counted twice.
  * counts are per-edit occurrences, not disjoint classes; an edit can contribute to several rows.

What is solid: the ordering. addComment, addArg/wrap and addParam dominate; error handling and
imports are real but modest -- which matches Teague's ergonomic case for addComment and puts
argument/parameter mutation at the centre of any mutator API.

### Mutator grammar: first spot test (2026-09-16)

`mutator/` -- card assembled from card_v1c's selector vocabulary, 20 reference mutations weighted
by the mined frequencies, all 18 distinct selectors validated to exactly 1 node first (which caught
M08: `.fn#validate_email .if` matches 2 guard clauses, so "the first check" was unanswerable --
the same failure as T19, caught by the same gate).

**Qwen3.5-9B, untuned, card only: parse 19/20, selector 16, op 18, args 8, fully correct 8/20.**

The grammar is learnable cold. Zero malformed answers; chained calls, clause builders and
`.finally()` all used correctly without examples of the latter. M17 produced a correctly ORDERED
two-handler wrapInTry, which was the property most at risk.

Selector 16/20 matches the pattern everywhere else in this project: the selector half is the strong
half once a card is present. **Argument FORM is the weak half (8/20)**, and part of that is the
judge being strict rather than the model wrong:

  * M04 `addArg({name: "retries", value: 3})` -- a structured form the card never showed
  * M11 `addParam("strict", "True")` -- two positionals instead of `"strict=True"`
  * M03 passed `"inside"` positionally though the card names the key `pos`
  * M09 `setReturn("copy(result)")` vs the reference `dict(result)` -- SEMANTICALLY FINE, scored
    wrong because arguments compare as exact strings. "Return a copy" has no single right answer;
    this is the transcription-vs-judgement problem the surface study flagged, now biting the
    reference set itself.

Two real failures: M08 substituted the wrong OPERATION (asked to change a guard's condition, it
produced `wrapInTry().on(...)`) -- a comprehension error, not a syntax one. M19 is the only
wrong_surface: `.mod.addImport(...)`, dropping the `$()` wrapper, and notably on `.mod`, the one
selector that is not a `.fn`/`.class`.

M06 inverted the design: `$('.fn#get_user').wrapCall('list', '.call#fetch_all')` puts the target in
the selector and the anchor in the arguments. Arguably more natural than the reference form, and
worth weighing before the grammar is treated as settled.

Gap: every fixture is Python, so addComment's language-derived syntax -- its strongest
justification -- remains untested.

### Published: qwen3.5-0.8b-astcss-t5 (2026-09-16)

https://huggingface.co/teaguesterling/qwen3.5-0.8b-astcss-t5 -- the tier-5 0.8B, merged from
`workspace/adapters/t5-langcard/epoch1`.

**Re-scored on the merged artifact rather than inheriting the adapter's numbers**, per the repo's
own rule that a merge is verified, not assumed. It reproduces the adapter exactly, tier for tier:

| eval | adapter (stage 10 e1) | merged & published |
|---|---|---|
| 108-pair | 82.4% (89/108), 17/21 20/25 28/31 24/31 | 82.4% (89/108), same tiers |
| eval_t5 | 83.6% (46/55) | 83.6% (46/55) |

`verify_merge`: 186 targeted tensors at max delta 0.0365, 134 untouched at 0.000488 (fp16
round-trip noise). A real merge, not a base passthrough -- the check that caught the silent no-op
where all 372 adapter tensors matched nothing.

Why this one is worth publishing: **34.5% -> 83.6% on eval_t5 at identical model size**, corpus the
only change. On that eval it beats a 4B trained on the old corpus (67.3%) and an untuned 9B (60.0%).
The 108-pair eval is saturated at this size and shows none of it -- old corpus, e1 and e2 all land
on exactly 89/108.

Caveats recorded on the model card: text-only (168 base tensors not written -- 153 `model.visual.*`
and 15 `mtp.*` dropped by save_pretrained under AutoModelForCausalLM), 0.0% without its card at
every size tested, and eval_t5's 55 pairs make a 2-pair difference noise.

`pipeline_tag: text-generation` is set deliberately: the device's import records
`model_task.source: hf_pipeline_tag`, so that is the field the Tiiny toolkit reads. It still cannot
be imported -- no `qwen3.5-0.8b` toolkit exists, only `qwen3.5-9b` -- so this publish is for sharing,
not deployment.

**Not published: the 4B** (`ladder-qwen3.5-4b-nf4-langcard/epoch2`, 89.8% on the 108-pair eval, our
best selector model). It trained under NF4, and merging an NF4-fitted adapter into fp16 is not
identity, so its number cannot be carried across -- it needs a merge plus a full re-score, and a 4B
generation pass is more GPU than stage 11 can spare. Queued for when the card frees.

### Published: qwen3.5-4b-astcss, and stage 11's epoch-1 score (2026-09-16)

https://huggingface.co/teaguesterling/qwen3.5-4b-astcss -- merged from
`ladder-qwen3.5-4b-nf4-langcard/epoch2`, upload verified complete (3 shards byte-identical to
local, 4,205,751,296 params, pipeline_tag text-generation).

**The merge is NOT identity, and the re-score is what proved it.** Scored in NF4 to match how the
adapter was measured:

| eval | merged & published | the adapter |
|---|---|---|
| 108-pair | **88.9%** (96/108) | 89.8% (97/108) |
| eval_t5 | **65.5%** (36/55) | 67.3% (37/55) |

One pair lost on each -- within noise, but real, and exactly what the repo's rule exists to catch.
`verify_merge` shows the mechanism: 248 targeted tensors at max delta 0.0031 against 178 untouched
at 0.00049, so the targeted deltas are only ~6x the fp16 round-trip floor. The fp16-trained 0.8B
merge gave ~75x (0.0365 vs 0.00049). An NF4-fitted adapter folded into fp16 lands much closer to
the noise, which is why carrying the adapter's number across would have been wrong.

**Corpus beats parameter count, stated on the model card itself.** On eval_t5 the 0.8B tier-5 model
scores 83.6% against this 4B's 65.5% -- five times smaller, 18 points better, because it trained on
a 7.4x larger corpus while this 4B trained on the old one.

### Stage 11 epoch 1 (4B on tier-5): the early scorer worked

The `astcss-stage11-e1score` unit fired autonomously at 22:59 when the epoch-1 adapter appeared,
waited for headroom (5,290 MiB free), scored both evals, and released the GPU -- the design worked
end to end without intervention.

| | 4B tier-5 e1 | 0.8B tier-5 e1 | 4B OLD corpus |
|---|---|---|---|
| 108-pair | **87.0%** (94/108) | 82.4% | 88.9% |
| eval_t5 | **83.6%** (46/55) | **83.6%** (46/55) | 65.5% |

val loss 0.0726.

Two readings. Tier-5 training lifted the 4B's eval_t5 from 65.5% to 83.6% (+18), confirming the
corpus is the binding constraint at 4B as well as 0.8B. But it **ties the 0.8B exactly** on that
eval -- 46/55 both -- while gaining only +4.6 on the saturated 108-pair. Five times the parameters
bought nothing on the eval that discriminates.

Epoch 2 is still running with ~383 min left. Stage 10's evidence was that epoch 2 LOST ground on
eval_t5 (83.6% -> 80.0%) with a better val loss, so the case for spending the GPU on it is weak --
killing it would free the card for stage 12 (the 9B, the only deployable target) tonight rather
than tomorrow evening.

### Stage 11 complete: epoch 2 wins, and I argued all day for killing it (2026-09-17)

The 4B on tier-5 finished on its own at 06:46:52, Result=success, both epochs and all four
scoring passes.

| | epoch 1 | epoch 2 |
|---|---|---|
| 108-pair | 87.0% | **90.7%** |
| eval_t5 | 83.6% (46/55) | **89.1%** (49/55) |
| val loss | 0.0726 | 0.0553 |

**90.7% is the best score in this project** -- above the published 4B's 88.9% -- and 89.1% on
eval_t5 beats every model measured, including cold haiku at 87.3%.

I recommended killing epoch 2 repeatedly, and built the early-scorer unit specifically to enable
that decision. The argument was stage 10's result that epoch 2 LOST ground on eval_t5
(83.6% -> 80.0%) with a better val loss, plus the reasoning that tier-5's single epoch already
carries 3.6x the gradient exposure of two old-corpus epochs. Both were wrong here: epoch 2 gained
+3.7 and +5.5 points, and val loss tracked the eval correctly. The stage 10 signal I leaned on was
2 pairs out of 55 -- I had called it noise when I first reported it, then used it as the basis for
a recommendation four separate times. Had it been taken, the best model in the project would not
exist.

The early-scorer apparatus itself worked exactly as designed (fired at 22:59 on adapter arrival,
waited for headroom, scored, released the GPU). The apparatus was sound; the decision rule it was
built to serve was not.

### The first card A/B was 10 pairs, not 55

`qualify.py run` stratified-samples by default (`--per-tier 10`). Running the A/B without
`--per-tier 0` gave each arm 10 of 55 pairs; arm v1 errored on one and scored 9. The resulting
77.8% vs 50.0% is a 2-3 pair difference and says nothing about the card.

A second error of mine on top: I first reported the arms had drawn DIFFERENT pairs, inferring it
from `n=9` vs `n=10` without opening the meta. `sample()` is deterministic on (per_tier, seed) and
both arms drew the SAME 10 ids. The invalidity is the sample size, not the sampling.

### The card A/B, finally run on all 55 pairs: v2 does not earn its place (2026-09-20)

The corrected A/B (`--per-tier 0`, both arms the untrained `Qwen/Qwen3.5-9B` on the device,
identical 55 pairs, identical engine binary, scored on the pinned `sd-20260914-1835` with the
fix127 macros -- only the card text differs):

| card | exec_match | |
|---|---|---|
| `card_t5.md` | 35/55 | **63.6%** |
| `card_t5_v2.md` | 31/55 | 56.4% |

Per pair: 30 both, 4 v1-only, 1 v2-only, 19 neither, plus one v2 arm pair (`t5-p03`) that
returned an empty completion -- a transport miss, not a card effect, which I am counting against
v2 in the table above but excluding from the test. On the 5 genuinely discordant pairs the exact
two-sided binomial is **p = 0.38**.

So the honest statement is not "v2 is worse". It is: **this A/B is underpowered, and what signal
there is points away from v2, so `card_t5.md` stays.** Five discordant pairs cannot distinguish a
7-point regression from noise; what they can do is rule out the reason v2 was written, which was
that adding a `.if` vs `if_statement` contrast would recover the three pairs haiku lost to exactly
that substitution. It recovered one (`t5-p29`) and cost four.

A caveat that limits how far this generalises: it was measured on the **untrained** 9B only. A
card line that does nothing for a base model may still matter for a tuned one, where the card is a
task trigger rather than a reference (stage 8). Nothing here says v2 is bad for a trained model --
only that there is no case for shipping it on this evidence.

One procedural note for future A/B scripts: `ab_card_t5.sh` sets the pinned engine inside
`score()` but not around `qualify.py run`, so `meta.json` records the *unpinned* paths and a null
`macros_sha256`. The scoring -- the part that decides the number -- did use the pin. The metadata
is misleading, not the result; worth fixing before the next arm, because it cost half an hour of
re-derivation to establish that the arms were comparable.

### The card cliff survives training on a mixed corpus (stage 10, arm 2)

Arm 2 trained the 0.8B on `t5-mixed`, a corpus that deliberately includes card-free rows, on the
theory that a model taught to work both with and without a card would stop depending on one.

| 108-pair | epoch 1 | epoch 2 |
|---|---|---|
| with `card_v1c.md` | 74.1% | **86.1%** |
| no card | 72.2% | 72.2% |

It did not work. At epoch 2 the card is still worth **+13.9 points** to a model explicitly trained
on card-free examples, and the no-card arm did not improve at all between epochs -- the second
epoch's entire gain went to the carded path. Mixing the corpus made the model better *with* a
card; it did nothing for the dependency itself.

Also worth recording against the epoch-2 argument: on this arm epoch 1 was the weak one
(74.1% -> 86.1%, +12). That is the opposite of the stage 10 arm-1 signal I built the "kill epoch 2"
recommendation on, in the same stage, on the same model.

### Stage 12: the 9B, and what it is and is not evidence for (2026-09-21)

The 9B ran, but not as planned. The langcard run was interrupted mid-training (the log ends in a
`KeyboardInterrupt` inside the forward pass) and was restarted on **`t5-mixed`** instead. So:

| | 9B `t5-mixed` e1 | 4B `t5-langcard` e2 | cold haiku |
|---|---|---|---|
| 108-pair | 88.0% (95/108) | **90.7%** | 94.7%* |
| eval_t5 | 87.3% (48/55) | **89.1%** | 87.3% |

\* haiku's 108-pair figure is 38 pairs, not 108.

**This is not "the 9B loses to the 4B".** The two differ in dataset as well as size, and `t5-mixed`
is the arm that was weak at one epoch everywhere it has been measured (at 0.8B: 74.1% at e1 vs
82.4% for langcard, only reaching 86.1% at e2). The 9B got one epoch of the weaker corpus and came
within 2.7 / 1.8 points of a 4B that got two epochs of the stronger one. A clean size comparison
needs `t5-9b-langcard`, which has never completed.

**Against the constraint that actually binds, it is the headline.** The device has a `qwen3.5-9b`
toolkit and no 4B one, so the 4B -- the better model -- cannot be deployed at all. Among things
that can be, 88.0% / 87.3% is the best measured, and it ties cold haiku on eval_t5 with a model
that runs on the device.

### The sitting_duck combinator defect in main's macros is fixed (measured 2026-09-23)

`verify.py` was patched on Sep 21 to fall back to `$SITTING_DUCK/src/sql_macros/css_selectors.sql`
when the `fix/127-combinator-steps` worktree is absent -- and that worktree has since been deleted,
so the fallback is now the live path for any run that does not set `ASTCSS_MACROS`.

That mattered, because main's macros were the subject of an open defect note: on 2026-09-14 every
two-step selector returned 0 rows under them. Re-measured today against main's current macros
(sha1 `3f3541d3`), the three cases from that note reproduce exactly:

    .try .call                    11  (want 11)
    .class#Animal .fn              5  (want 5)
    .class#DatabaseConnection .fn  5  (want 5)

So the fallback is safe and the note can be dismissed. Every stage 10/11/12 and A/B number in this
file was nonetheless produced with `ASTCSS_MACROS` pinned to `sd-20260914-1835`'s fix127 copy, so
none of them depend on this either way.

### Stage 13: the clean size comparison, and the 9B loses it (2026-09-24)

The 9B on `t5-langcard`, two epochs — identical to stage 11's 4B in dataset, epochs, accum, lr and
seed, so **model size is the only variable**. This is the comparison stage 12 could not make.

| | 108-pair (tiers 1-4) | `eval_t5` | val loss |
|---|---|---|---|
| 4B langcard e1 | 87.0% — 19/21 21/25 28/31 26/31 | 83.6% | 0.0726 |
| **4B langcard e2** | **90.7%** — 19/21 22/25 29/31 28/31 | **89.1%** | 0.0553 |
| 9B mixed e1 | 88.0% — 19/21 21/25 27/31 28/31 | 87.3% | 0.0700 |
| 9B langcard e1 | 72.2% — 17/21 19/25 24/31 **18/31** | 89.1% | 0.0678 |
| 9B langcard e2 | 87.0% — 18/21 21/25 29/31 26/31 | 87.3% | **0.0453** |

**Twice the parameters, same corpus, same recipe — and it is worse on both evals.** 87.0% vs 90.7%
and 87.3% vs 89.1%. It is also no better than the 9B trained on the *weaker* corpus for *one*
epoch (88.0% / 87.3%), so at 9B the corpus stopped mattering too.

**Val loss went the other way, decisively.** The 9B beat the 4B at both epochs (0.0678 vs 0.0726,
0.0453 vs 0.0553) and lost on both evals at both epochs. In the stage 11 write-up I cited val loss
tracking the eval as corroboration that killing epoch 2 would have been wrong. That was true
*within* a run and is now shown to be false *across* sizes: a 9B fits this corpus better and
selects worse. Nothing here should be decided on val loss again.

#### The epoch-1 collapse is `:has()`, not noise

72.2% with tier 4 at 18/31 looked like a broken run. It is not — tier 4 is the `:has()` tier, and
**epoch 1 of the 9B has not learned `:has()` yet.** It writes a descendant combinator or a bare
name where the reference wants containment:

    t4-p07   e1 `.fn .throw`              e2 `.fn:has(.throw)`            ✓
    t4-p31   e1 `.loop .call#append`      e2 `.loop:has(.call#append)`    ✓
    t4-p12   e1 `.fn#open`                e2 `.fn:has(.call#open)`        ✓
    t4-p23   e1 `with_statement .call#write`  e2 `with_statement:has(.call#write)` ✓

Nine of the thirteen tier-4 misses flip to correct at epoch 2. The 4B already had `:has()` at
epoch 1 (26/31). So the second epoch is doing something specific and legible at 9B — acquiring one
construct — rather than generally tightening.

The mirror image: epoch 1 scored *higher* on `eval_t5` (89.1% vs 87.3%), which is one pair and is
noise. Read together, the honest summary of epoch 2 at 9B is "+14.8 on the 108 by learning
`:has()`, flat on eval_t5".

#### What this means for the device

The 9B is still the only deployable size — the device has a `qwen3.5-9b` toolkit and no 4B one —
so 87.0% / 87.3% remains the best number we can actually ship, and it ties cold haiku on `eval_t5`.
But it should be shipped knowing the 4B beats it, that the gap is the model and not the data, and
that spending 15.5 h of GPU to find this out was the point of running it.

### The fluent-mutation corpus taught the mine and destroyed the capability (2026-09-24)

Two adapters were trained on `workspace/datasets/fluent-mutations` (11,550 rows mined from edit
history) on Sep 21-22 and never scored. Scored now, on two suites:

- **held** — 300 sampled rows of the never-trained `val.jsonl`, each carrying **its own** system
  card, because the corpus has two variants (9,282 / 2,268 rows) and substituting one for both
  would confound the card with the model.
- **ref** — the 20 hand-written tasks in `mutator/tasks.json`, written before any of this existed.

| | held ALL | ref ALL | held selector / op / args |
|---|---|---|---|
| base 0.8B (no adapter) | 1.0% | 10.0% | 13.0 / 10.0 / 4.7 |
| **fluent-0.8b e1** | **47.3%** | **0.0%** | 87.7 / 54.3 / 85.7 |
| base 4B (no adapter) | 4.0% | **45.0%** | 29.7 / 15.3 / 10.7 |
| **fluent-4b e1** | **47.0%** | **0.0%** | 87.0 / 54.3 / 85.7 |

**Training made both models strictly worse at the hand-written tasks than doing nothing.** The
untrained 4B, given the card cold, gets 45% of the 20 reference tasks fully right. After a full
epoch on 11,550 mined rows it gets **zero**. The 0.8B went 10% → 0%.

Meanwhile in-distribution it looks like a triumph: 4.0% → 47.0%, with parse validity 100% (against
the base's 47.3%, which included 150 unknown-op answers). The corpus taught the grammar perfectly
and taught the mine's distribution along with it.

#### It is not card mismatch — I checked, because it was the obvious alternative

The ref suite normally uses `mutator/card.py`'s card, which no training row carried. Re-running ref
with the card the majority of training rows *did* carry:

| ref, 4B | card.py card | corpus card |
|---|---|---|
| base | 45.0% | 30.0% |
| fluent-4b e1 | 0.0% | 0.0% |

The trained model scores 0/20 under **both** cards. The base scores 45% and 30%. So the collapse is
the fine-tune, not the prompt. (Secondary: `card.py`'s card is the better card for an untrained
model, 45% vs 30% — worth knowing before the corpus cards get treated as canonical.)

#### What the failures look like

Two distinct modes on ref, both absent in-distribution:

    M01  want addComment(...)   got  $('.fn#search_users').flagSQLInjection()
    M04  want addArg("retries=3")  got  $('.fn#create_connection').retry(3)
    M06  want wrapCall("list")  got  $('.fn#get_user .call#fetch_all').wrapInList()

...inventing a plausible op that does not exist — note the selector is often *exactly* right, so
it is the operation vocabulary that has gone — and:

    M02, M03, M08, M09  ->  $('.fn').addArg()

...collapsing to one generic answer. Five of the first ten ref tasks got `$('.fn').addArg()`.

#### Size bought nothing again

0.8B and 4B land on held at 47.3% and 47.0%, with **identical** op (54.3%) and args (85.7%)
figures to the decimal. Five times the parameters, the same score. That is the third time in this
project the ceiling has turned out to be the data: the selector ladder flattened at 4B→9B, the
tier-5 9B lost to the 4B, and now the mutator does not move with size at all.

#### The honest state of the mutator track

The grammar is learnable — 87% selector accuracy and 100% parse validity in-distribution is not
nothing. But **op selection is the bottleneck at 54.3%**, roughly coin-flip, while the selector
beside it is at 87%: the model finds the right nodes and then does the wrong thing to them. And the
corpus as mined cannot be trained on as-is without losing more than it gives.

Next step is not another training run. It is the corpus: 35 ops with a long tail
(`replaceWith` 1823, `addComment` 1702 ... `addField` 125, `addImport` 124), mined labels of unknown
fidelity, and no held-out set that is independent of the mining. Fix the corpus, then train.

#### A stale judge, left alone

`mutator/judge.py`'s `OPS` set (13 ops, including `setCondition`) predates the corpus, which has
35 ops, uses `addCondition`, and whose single most common op — `replaceWith` — is absent from `OPS`
entirely. `judge.judge()` would bucket every one of those "malformed" however correct the answer,
so `mutator/score_fluent.py` derives the op vocabulary from the corpus and uses `judge.score()`,
which is op-agnostic (it parses both sides and compares). `judge.py` belongs to in-flight work from
another session, so it is reported here rather than edited.

### Correction: every fluent training row was truncated, and it ate the front of the card (2026-09-25)

The section above concludes that the fluent corpus "taught the mine and destroyed the capability."
That conclusion was premature. The measurement was real; the cause I assigned to it was wrong.

Both fluent runs trained with `--max-len 1024` (the default). Measured over 3,000 rows with the
4B's own tokenizer:

    TRUE total length   median 1471   p90 1603   p99 1612   max 1619
    system card         median 1435   max 1562
    answer              median    7   max   26

    cap 1024 -> 100.0% of rows truncated
    cap 2048 ->   0.0% of rows truncated

**Every single row was over the cap.** And `encode()` truncates from the FRONT:

    ids = (prompt_ids + answer_ids)[-max_len:]

which keeps the answer and the request and throws away roughly the first 400 tokens of a
1,435-token system card — in all 11,550 rows. The card was never shown whole, not once.

The training logs said so and nobody read it. `train rows 11550 (median 1024 tokens, max 1024)`:
a median that equals the cap exactly, and a max that equals it too, is the signature of universal
truncation, not of a corpus whose rows happen to be that long. Compare the tier-5 selector corpus
in the same field: `median 580 tokens, max 670` — comfortably under, never clipped. That is why
the selector track was clean and this one was not.

#### It explains every symptom I attributed to the corpus

- **Invented ops** (`flagSQLInjection`, `retry(3)`, `wrapInList`) — the op table lives in the part
  of the card that was cut.
- **Op 54.3% against selector 87.7%** — the semantic-class list and the op list sit in different
  places in the card; whichever survived at the tail is what got learned.
- **Collapse to `$('.fn').addArg()`** — a degenerate answer is what a mutilated prompt teaches.
- **0.8B and 4B identical to the decimal** (op 54.3%, args 85.7%) — both were handicapped
  identically by the data pipeline, so the ceiling was the truncation, not the parameter count. I
  filed that as the third instance of "size buys nothing." It was not one.
- **The base beating the fine-tune on hand-written tasks (45% -> 0%)** — at inference the full card
  is supplied, and the base can read it. The fine-tune was trained to expect a beheaded card, so it
  was also evaluated under a train/test mismatch that nothing in the scoring flagged.

#### What is actually known now

Known: those two adapters are void as evidence about the corpus. The truncation is sufficient on
its own to produce what was measured.

NOT known: whether the mined corpus is any good. That question has never been tested, because the
only test of it was invalid. The 54.3% op figure, the 47% held-out number and the 0/20 on the
reference set should all be treated as measurements of a broken pipeline.

#### The cheap fix, and the guard that should have existed

`--max-len 2048` puts 0% of rows over the cap. That is the whole fix; retraining at 2048 is the
first real test the corpus has had.

The guard: `encode()` should count how many rows it truncates and the trainer should refuse, or at
minimum shout, when that fraction is not near zero. A silent front-truncation that removes the
system prompt is not a degradation, it is a different experiment — and the summary line the trainer
already prints contained the evidence all along.

### Stage 15: the truncation was real, and it was not the whole story (2026-09-25)

The fluent 0.8B retrained at `--max-len 2048`, the only variable changed. `train rows 11550
(median 1473 tokens, max 1619)` — the cap is gone and the card reached the model whole for the
first time.

| | truncated (1024) | fixed (2048) |
|---|---|---|
| held-out ALL | 47.3% | **54.3%** |
| held-out selector | 87.7% | 87.7% |
| held-out op | 54.3% | **55.0%** |
| held-out args | 85.7% | **92.7%** |
| reference set (20 hand-written) | 0.0% | **0.0%** |

**The truncation was real and cost seven points**, almost all of it in the argument column
(85.7% → 92.7%). That is what you would expect from restoring the head of a card: the parts of
the grammar that were cut come back.

**And it explains neither of the two things I blamed on it.**

*Op selection did not move.* 54.3% → 55.0%, still barely better than a coin flip, sitting beside
a selector column at 87.7% that did not move either. I wrote that the invented ops
(`flagSQLInjection`, `wrapInList`) were caused by the op table being in the truncated region. With
the whole table present, op accuracy is unchanged. That hypothesis is dead.

*The reference set is still zero.* 0/20, exactly as before, against an untrained 0.8B that scores
10% and an untrained 4B that scores 45%. Fine-tuning on this corpus still makes a model strictly
worse at hand-written tasks than doing nothing.

#### I over-retracted

The first write-up concluded the corpus taught the mine and destroyed out-of-distribution
capability. The second retracted that entirely, called the adapters "void as evidence", and said
whether the corpus is any good was "untested". With the confound removed, the original conclusion
survives in its load-bearing parts:

- the corpus does teach the mined distribution well (47.3% → 54.3%, parse validity 100%)
- op selection is a genuine bottleneck at ~55%, not an artifact of the pipeline
- the out-of-distribution collapse to 0/20 is genuine, not an artifact of the pipeline

What the truncation correction legitimately bought was seven points and the knowledge that the
first numbers understated the corpus. What it did not buy was an excuse. Both of the failures that
made the corpus look harmful are still there.

The right order was: fix the confound first, *then* conclude. I did it backwards twice — concluded
before checking the confound, then retracted further than the evidence warranted.

#### What this means for the mutator track

Unchanged from the original recommendation, now on firmer ground: **the corpus needs fixing, not
scaling.** A larger mine of the same labels buys a model that is more confident about the wrong
operation. The next artifact is an execution harness that can apply a proposed mutation and check
the result — `mutator/engine.py` already registers 32 operators that do the applying, and nothing
has ever wired it into scoring.

### The seed replicate that was in the repo all along (2026-09-27)

Building a separate teaching corpus surfaced a methodological problem that applies straight
back here, and the evidence for it was already on disk.

`small-langcard` and `small-langcard-seed18` are the **same configuration** — same dataset
(`all-langcard-cap8`), same `epochs 2, lr 2e-4, rank 16, alpha 32, accum 16, max_len 1024,
quant none`. The only difference is `seed` 17 against 18. Nobody ever compared them as a seed
experiment.

| eval | seed 17 | seed 18 | difference |
|---|---|---|---|
| 108-pair | 81.5% | 82.4% | +0.9 pts (1 pair) |
| **eval_t5** | 34.5% | 30.9% | **−3.6 pts (2 pairs)** |
| val loss | 0.2832 | 0.3548 | — |

**±3.6 points on eval_t5 from the training seed alone.** That is the resolution floor of the
instrument, measured rather than assumed, and it is larger than several conclusions in this
file.

#### Which claims sit below it

| comparison on eval_t5 | gap | |
|---|---|---|
| 4B e2 vs 9B e2 — "twice the parameters, worse" | 1.8 | below the floor |
| merged 4B vs its adapter — "the merge lost nothing" | 1.8 | below the floor |
| 9B langcard vs 9B mixed — "the corpus stopped mattering at 9B" | 0.0 | below the floor |
| 4B e2 vs cold haiku — "it beats a frontier model cold" | 1.8 | below the floor |
| 4B e1 vs e2 — "epoch 2 is the best model" | 5.5 | above |

So the stage 13 headline — **the 9B loses to the 4B** — is supported on the 108-pair eval
(3.7 points, 4 pairs, against a 0.9-point seed effect there) and **is not supported on
eval_t5**, where the 1.8-point gap is half the seed noise. I wrote it as though both halves
were evidence. One half was.

The epoch-2 conclusion survives: 5.5 points on eval_t5 and 3.7 on the 108-pair, both above
their respective floors. The "I argued four times for killing it and was wrong" account stands.

#### What this does not mean

It does not mean the numbers are wrong — they are correct measurements of single runs. It
means a 1-to-2-pair difference on a 55-item eval is not a difference, and this project has
repeatedly treated one as though it were. I did it again on the workshop corpus a week later,
with a cleaner instrument, and had to retract a headline over it.

#### The cheap fixes, in order

1. **Two seeds on any comparison that decides something.** One extra run per arm. The
   comparisons above that matter — 4B vs 9B especially — deserve it before they are cited
   again.
2. **Print the eval's resolution beside its score.** `89.1% (49/55; 1 pair = 1.8 pts)`. It
   costs nothing and it would have stopped most of this.
3. **Grow eval_t5.** 55 items is a 1.8-point quantum, and the best models now miss five of
   them. The eval, not the model, is the binding constraint on every remaining question.

#### What else the workshop corpus is worth borrowing

**Measure the corpus's reachable space.** The workshop's first generator could only produce
1,512 distinct pairs, so 1,200 training rows was 79% of everything there was — an enumeration
with repeats, which produced a dramatic and entirely artefactual result. The tier-5 corpus here
is healthier — 15,928 rows carry 15,551 distinct (request, answer) pairs — but it holds only
**4,765 distinct answers**, so each selector appears about 3.3 times under different phrasings.
Worth knowing before concluding anything about corpus size.

**Decompose the selector eval by construct.** The mutator work already reports selector / op /
args separately, and that split is where its one genuinely diagnostic finding came from
(selector 87.7%, op 55.0%). The selector evals still report a single `exec_match`. A per-construct
breakdown — `:has`, `:not`, combinators, attributes, `::callers` — would turn "90.7%" into a list
of what to fix, and cost nothing but a grouping in the scorer.

### Five seeds, and a 270M rung on the ladder (2026-09-28)

Two runs, both prompted by the seed replicate found on disk.

#### The seed effect is bigger than the one accidental pair suggested

Three more seeds on the identical `small-langcard` config — same dataset, `epochs 2, lr 2e-4,
rank 16, alpha 32, accum 16, max_len 1024, quant none` — bringing it to n=5:

| seed | 108-pair | eval_t5 |
|---|---|---|
| 17 | 81.5% (88/108) | 34.5% (19/55) |
| 18 | 82.4% (89/108) | 30.9% (17/55) |
| 19 | 79.6% (86/108) | 38.2% (21/55) |
| 20 | 83.3% (90/108) | 34.5% (19/55) |
| 21 | 78.7% (85/108) | 32.7% (18/55) |

| | mean | sd | **range** |
|---|---|---|---|
| 108-pair | 81.1% | 1.92 | **4.6 pts** (5 pairs) |
| eval_t5 | 34.2% | 2.70 | **7.3 pts** (4 pairs) |

The n=2 estimate was 0.9 and 3.6 points. With five seeds it is **4.6 and 7.3** — the single
accidental pair happened to be close together on the 108-pair eval, and understated the spread
on both. Two seeds are not enough to characterise this either.

So the resolution floor is worse than yesterday's entry said. On the 108-pair eval a 4-pair
difference is inside the noise; on eval_t5, so is a 4-pair difference. Every comparison in this
file that rests on fewer than five pairs of difference, on a single run per arm, should be read
as "no difference detected" rather than as a result.

That includes the stage 13 headline on **both** evals, not just eval_t5 as yesterday's entry
concluded: the 4B-vs-9B gap is 3.7 points on the 108-pair against a 4.6-point seed range. I
corrected that claim once and did not correct it far enough.

#### The ladder goes down to 270M, and the easy eval cannot see it

`gemma-3-270m-it` on tier-5, same recipe, bf16 (it NaNs in fp16), two epochs, 4.9 h:

| model | params | 108-pair | eval_t5 |
|---|---|---|---|
| **gemma-3-270m** | **0.27B** | **78.7%** | **67.3%** |
| Qwen3.5-0.8B | 0.8B | 82.4% | 83.6% |
| Qwen3.5-4B | 4B | **90.7%** | **89.1%** |
| Qwen3.5-9B | 9B | 87.0% | 87.3% |

**On the 108-pair eval the 270M model is 3.7 points behind the 0.8B — inside the 4.6-point seed
range.** A quarter-billion-parameter model is not distinguishable from one three times its size
on that eval, and sits twelve points off the best model in the project at a fifteenth of the size.

**On eval_t5 it is 16.4 points behind the 0.8B**, far outside the 7.3-point range. The harder
relational eval separates them cleanly where the easier one cannot.

That is the sharpest statement of the project's own thesis so far. The 108-pair eval has been
saturated for some time; it can no longer tell a 270M model from a 4B one to within its own noise.
**eval_t5 is the only instrument here still measuring anything**, and it is 55 items with a
1.8-point quantum.

#### Two caveats that are gemma's doing, not choices

**The card is not in the system position.** Gemma's chat template has no system role; it folds
the card into the first user turn. Every other run in this file put the card in the system
position. Given that the card is a task trigger before it is a reference, card placement is a
live alternative explanation for gemma's eval_t5 deficit, and it has not been tested.

**bfloat16, emulated.** Gemma-3 NaNs in float16 — 60 of 60 steps skipped, adapter unchanged,
loss still printing — and this box is sm_75 with no native bf16.

Cold, before training, it scored 0.0% and emitted Python function definitions rather than
selectors. The whole 78.7% is the corpus's doing.

#### What to do about the eval

Every remaining question in this project is now noise-limited rather than model-limited. Before
another training run:

1. **Grow eval_t5.** At 55 items nothing smaller than 4 pairs is visible. The 448 pairs held on
   upstream defects are the obvious source, and the combinator defect that blocked many of them
   is fixed.
2. **Report resolution beside score.** `83.6% (46/55; 1 pair = 1.8 pts; seed range ≈ 7 pts)`.
3. **Two seeds minimum on any comparison that decides something** — and five if it is going to be
   written down as a finding.

### `:scope` resolved, and a card that teaches a selector the engine cannot run (2026-09-28)

Six attempts. The answer was a distinction between two spellings that this file, the card and
the oracle each half-recorded.

```
.fn::scope                      -> 84 nodes    axis form, no argument. WORKS.
.fn:in-scope(.class#Animal)     ->  5 nodes    argument form. WORKS, and equals .class#Animal .fn
.fn:scope(.class#Animal)        ->  0 nodes    accepted as a pseudo-class, returns nothing. ALWAYS.
.fn:totally_made_up(.class#X)   ->  ERROR      "unknown pseudo-class"
```

`:scope(X)` is **silently unimplemented**. It does not error the way an invented pseudo-class
does — it is recognised and then returns the empty set for every input. That is why five
previous attempts to measure it produced nothing: there was nothing to measure, and no error
saying so.

#### The card and the corpus disagree

| | uses |
|---|---|
| `card_t5.md` line 60 | **`:scope(.class#Name)`** — the form that returns nothing |
| tier-5 training corpus | **`:in-scope(`** — 510 answers, and **zero** `:scope(` |
| eval_t5 | 3 pairs written as `:scope(`, with oracle references of 3, 2 and 10 nodes |

So the card documents one spelling, every training example shows another, and the eval asks in
the card's spelling while scoring through the oracle. A model that follows the card faithfully
writes a selector that returns nothing.

**Fix the card line to `:in-scope(.class#Name)`.** It is one line, and it is currently teaching
a construct that cannot execute.

#### And the `>` substitution is not a scoring artifact

This file has said twice that "both model families substitute `>` and both are scored wrong",
with the implication that the scoring was at fault. It is not. On the three `:scope` pairs:

```
t5-p42  want .fn:scope(.class#Cat)
        4B     .fn:in-scope(.class#Cat)              PASS
        haiku  .class#Cat > .fn                      FAIL
t5-p44  want .var:scope(.fn#create_index)
        4B     .var:in-scope(.fn#create_index)       PASS
        0.8B   .fn#create_index > .var               FAIL
```

The oracle accepts `:in-scope` as equivalent and rejects `>`, correctly: `>` is direct-child
only, while scope containment reaches any depth. The models answering `>` are simply wrong, and
the ones answering `:in-scope` — the form they were trained on — are marked right. The scoring
works. The open question was never a scoring question.

#### The assessment error that surfaced all this

I retired eval pair t5-p55 (`.fn#level2::callees`) on the grounds that it returned the same
nodes as `.fn#level2 .call`, and therefore "does not test `::callees` at all".

That inference was wrong. Equal node sets on one fixture mean **either** the pair is vacuous
**or** the two selectors coincide there. `oracle.py` documents `::callees` as "the named calls
inside the matched function, nested functions included" — which is exactly what the pinned
engine returns and exactly what the pair's request asks for. On `deep_nesting.py` every call is
named, so a descendant selector happens to match. The pair is **weak**, not vacuous, and its
reference is correct against documented semantics. Restored the same day.

Worth generalising, because `verify.py`'s relaxation check makes the same inference
automatically: **it cannot distinguish "this component does nothing" from "this component
happens to do nothing on this fixture".** A pair it calls vacuous deserves a look at the
documented semantics before it is dropped, and a construct that is broken in the engine will
make every pair using it look vacuous.

(Separately: sitting_duck main now returns 1 node for `.fn#level2::callees` where the pinned
engine returns 5, which contradicts the oracle's documented "nested functions included". That
looks like an upstream regression and is worth reporting.)

## The call-graph pseudo-forms are near-synonyms of their syntactic lookalikes, fixture-dependently

t5-p55 -- `.fn#level2::callees` credited to a model that answered `.fn#level2 .call` -- was not
a one-off. Mining all seven rebase120 runs for predictions that earned `exec_match` with a
DIFFERENT string turns up 24 of the 98 pseudo-form eval pairs in the same shape:

    :called-by(X) <- .fn#X .call         8 pairs
    :calls(X)     <- :has(.call#X)       5
    ::callees     <- .fn#X .call         4
    ::callers     <- :has(.call#X)       3
    :scope(X)     <- descendant / :in-scope(X)   3
    :is-called    <- :has(.call)         1

A further 13 are conjunction reordered (`:not(A):has(B)` vs `:has(B):not(A)`). Those are
genuinely equivalent and correctly credited; they are not defects and are not counted above.

### What the engine actually does (train/audit/probe_pseudo.py, pinned sd-20260914-1835)

Every form the card teaches, five fixtures, each compared against its bare form:

    :has :not ::callers :is-called :calls :exported :is-referenced ::scope   discriminates 5/5
    ::callees   4/5 (VACUOUS on py-blq)    :typed  4/5    :called-by()  3/5
    :in-scope(.class)   ERRORS 5/5 -- "ast_select: unknown"; it requires a NAMED argument
    :scope(.class)      VACUOUS 5/5 -- returns exactly `.fn`, the constraint ignored
    :decorated :async   zero nodes on the 3 non-Python fixtures (language-specific, not traps)

TWO EARLIER CLAIMS IN THIS FILE ARE WRONG, and this is the correction:

1. ":scope(X) always returns 0, so it is silently unimplemented" was drawn from one argument
   (`.class#Animal`). With a named argument `:scope` is neither vacuous nor empty --
   `.fn:scope(.class#Cat)` is 3 nodes on py-variety, not 84 and not 0. It is vacuous only with
   an UNNAMED argument. Its actual semantics remain unpinned. The consequence: the queued
   one-line change to card_t5.md:60 would have "fixed" a line that is not broken. Do not make it.

2. "a fixture with a nested call would make ::callees diverge from a descendant .call" is
   wrong. oracle.py:722 documents ::callees as including nested functions, and the descendant
   form includes them too. They part company over how the call graph resolves a name, which is
   fixture- and target-specific and cannot be predicted from the fixture's shape.

### The gate answers it per target, and the answer is usually "no distinction"

140 contrastive candidates (five fixtures, six named targets each), each side declaring the
other as its distractor, run through verify.py's engine gate:

    ACCEPTED  24        rejected 116: distractor ties 86, node bounds 38, errors 6

`:calls(X)` tied `:has(.call#X)` on 32 of 32 -- on this engine it is not call-graph-resolved,
and there is no distinction to teach. `::callers` tied on 23 of 32, `::callees` on 23 of 30.

So the finding is not that the eval is broken. It is that ON THE PINNED ENGINE these forms are
usually extensionally EQUAL to their syntactic lookalikes, and diverge only on particular
targets. Where they coincide, crediting the lookalike is correct and the pair tests nothing.
Where they diverge the distinction is real -- and only a per-target engine check can say which.

### The three `:scope` pairs are a different defect: they are not scored by the engine

13 of the 120 eval_t5 pairs carry `reference.source == "oracle"`, and `qualify.score` branches
on that: an oracle-sourced pair is scored against oracle.py's Python model of the semantics,
not against the engine. All three `:scope` pairs are oracle-sourced. The engine says
`.call:scope(.fn#load)` and `.fn#load .call` return DIFFERENT node sets; the oracle's model
equates them, which is why six models answered the descendant form and were credited. Those
pairs are simultaneously non-discriminating and measured by something other than the engine.

### What this means for reading the ladder

The audit (workspace/audit_eval_pseudo.py, engine, mined near-misses declared as distractors)
says 23 of the 46 probed pairs cannot withhold credit from the near-miss. Any gain a model
makes on those pairs is invisible, because both the right and the wrong answer score correct.
So a full-eval exec_match delta is not the number to read for this distinction -- the
discriminating subset and the near-miss rate are.

Engine identity is recorded with every accepted pair: these encode PINNED semantics, and
`::callees` is contested between pinned and sitting_duck main (main returns 1 node for
`.fn#level2::callees` where pinned returns 5).

## The contrastive pseudo batch taught the TEMPLATE, not the distinction

Same-seed A/B on the 0.8B. Arm A is the 15,928-row baseline; arm B is the identical corpus
plus 55 contrastive pseudo-form pairs (109 offered, `--cap-template 8` admitted 55). Verified
each launch: 0 rows displaced from A, 0 held-out pairs leaked into B. Both arms 2 epochs,
seed 18, max-len 1024, card_v1c for training. Val losses are indistinguishable
(A 0.0823/0.0581, B 0.0858/0.0587), so this is not an over/under-fitting story.

### The headline looks decisive and is misleading

eval_pd -- 43 held-out pairs, every one engine-confirmed to discriminate:

    arm            exec     lookalike
    base epoch1   74.4%       2/43
    base epoch2   67.4%       4/43
    plus epoch1   97.7%       0/43
    plus epoch2  100.0%       0/43

+32.6 points and every lookalike gone. But eval_pd was held out BY TARGET, not by PHRASING:
its requests are the same six NL templates the training pairs use, with a different function
name substituted. So 100% is consistent with completing a memorised template, and does not
by itself show the semantic distinction was learned.

### On independently written requests there is no transfer, and a small regression

eval_t5's 118 requests were written by a separate process (batches b1/b2/b3), not from this
generator's templates. There, arm B at epoch 2 is 3 pairs won, 5 lost:

    metric                 base e1  plus e1   base e2  plus e2
    full (118)              81.4%    84.7%     85.6%    83.9%
    pseudo subset (98)      89.8%    90.8%     95.9%    92.9%
    DISCRIM subset (83)     83.1%    80.7%     83.1%    79.5%

The discriminating subset -- the only one where the distinction can be scored -- is WORSE for
arm B at both epochs (-2.4 and -3.6). Small, one seed, so not a demonstrated regression; but
there is no evidence of benefit where the wording is not ours.

The clinching case is t5-p153, `.fn:not(:is-called):has(.member)`. Arm A answers it correctly.
Arm B answers `.fn:not(:has(.call)):has(.member)` -- the exact lookalike substitution this
batch exists to teach out, on a pair that discriminates, introduced BY the batch.

### The near-miss metric I built is flawed: it does not weigh cost

I proposed the lookalike rate as "the sensitive number". Broken down, arm A's 7 lookalike
answers are ALL on non-discriminating pairs and ALL exec_match TRUE -- on those pairs the
lookalike returns the reference's nodes, so answering it is correct and costs nothing. Arm B's
2 are one costless (t5-p55) and one WRONG on a discriminating pair (t5-p153).

So "7 -> 2" is not an improvement. The metric counts lookalike answers without asking whether
the pair can penalise them, and on this eval most cannot. A corrected metric must count only
lookalike answers on pairs the engine says discriminate. By that measure arm A scores 0 and
arm B scores 1 -- the batch made it worse.

### What this costs and what it implies

11.6 h of GPU (two arms, two epochs, with the causal_conv1d kernel at ~11%). The verdict:
generating contrastive pairs from a handful of NL templates teaches the templates. The gate
was right about which SELECTOR pairs discriminate; the weakness was entirely in the request
wording, where 152 pairs drew on six phrasings.

Two testable consequences, neither run yet:
- Hold out by TEMPLATE rather than by target. If eval_pd's gain survives that, the
  distinction generalises; if it collapses toward the eval_t5 result, it was memorisation.
- Diversify the NL an order of magnitude (~20 phrasings per contrast) before retrying. That
  also lifts the `--cap-template 8` ceiling that discarded 97 of 152 pairs -- template poverty
  and the cap are the same defect seen from two sides.

### CORRECTION: it was not template memorisation. It is a language trade.

The section above concluded the batch "taught the template, not the distinction". The
falsification test refutes that, and a subset breakdown explains the apparent contradiction.

**Test 1 -- re-word the eval.** eval_pd2 is the same 43 pairs, same fixtures, same
engine-verified references, with every REQUEST rewritten to share no phrasing with training
(`.fn#X::callees` asked as "resolve the call graph out of X and list what it reaches" rather
than "the calls X makes, resolved through the call graph"). Adapters unchanged; only the
English differs.

    arm            eval_pd (train wording)   eval_pd2 (re-worded)
    base epoch1           74.4%                    58.1%
    plus epoch1           97.7%                    90.7%
    base epoch2           67.4%                    53.5%
    plus epoch2          100.0%                    81.4%

Both arms degrade on unseen wording, but the GAP survives: +23.3 -> +32.6 at epoch 1,
+32.6 -> +27.9 at epoch 2. A memorised template would have collapsed the gap, not held it.
The batch teaches something that generalises across surface form.

**Test 2 -- which eval_t5 pairs could it have helped?** Splitting eval_t5 by whether a pair
uses a call-graph form AND discriminates:

    subset                            n    base e2   plus e2
    all                             118     85.6%     83.9%   -1.7
    call-graph forms (any)           38     94.7%     92.1%   -2.6
    call-graph AND discriminating    18    100.0%     88.9%  -11.1
    discriminating, non-call-graph    65     78.5%     76.9%   -1.5

The baseline already scores 100% on exactly the pairs the batch targets. There was no headroom
on eval_t5, and arm B gave 2 of those 18 pairs back.

**The reconciliation is language.** eval_t5 is entirely py-variety and repo-small-py, i.e.
Python -- the dominant language in the training corpus. eval_pd/pd2 are mostly NOT Python
(java 8, js 18, rust 10, go 3, bash 2, python 2 of 43). So:

  - on PYTHON the baseline had already learned the call-graph distinction (94-100%), and the
    batch REGRESSED it (-11.1 points at epoch 2, 2 pairs of 18)
  - on the other five languages the baseline was weak (53-74%) and the batch fixed it
    (+28 to +33 points, robust to re-wording)

That is a trade, not a failure and not a win: real transfer where the model was weak, a real
cost where it was already strong. Reported as a single eval_t5 number it reads as a small
regression, which is why the Python-only headline eval cannot see what this batch did.

What stands from the earlier section: the near-miss metric IS flawed (arm A's 7 lookalike
answers were all costless, on pairs where the lookalike returns the reference's nodes), and
`--cap-template 8` admitting only 55 of 152 pairs IS template poverty. What does NOT stand is
the memorisation verdict.

## sitting_duck silently DISCARDS pseudo-class arguments (third instance)

Measured on the pinned engine, py-variety:

    .fn:decorated                       2 nodes
    .fn:decorated(by="property")        2 nodes   IDENTICAL to bare
    .fn:decorated(by="zzzznotathing")   2 nodes   IDENTICAL to bare
    .fn:decorated(property)             2 nodes   IDENTICAL to bare
    .fn[annotation*="property"]         1 node    (the actual answer)

    .fn:typed                           9 nodes
    .fn:typed(None)                     9 nodes   IDENTICAL to bare
    .fn:typed(Zzzznotatype)             9 nodes   IDENTICAL to bare
    .fn[signature="None"]               1 node    (the actual answer)

The parenthesised argument is parsed, thrown away, and the bare form's result returned. A
deliberately nonsense argument behaves exactly like a real one, and nothing errors. This is
the same failure as `:scope(X)` being vacuous with an unnamed argument -- the THIRD form found
to accept and discard an argument. Worth reporting upstream: it makes an entire class of
selector mistake unobservable.

### It also manufactured a false pass in the eval

t5-p31 wants `.fn[annotation*="classmethod"]`. With the arity card the 9B answered
`.class .fn:decorated(by="method")` and EXEC-MATCHED -- because that reduces to
`.class .fn:decorated`, which happens to return the same single node as
`.class .fn[annotation*="classmethod"]` on this fixture. The pair credited an invented form by
coincidence, so t5-p31 belongs with the non-discriminating pairs.

### The card cannot fix this; the weights have to

Same 9B adapter, card_t5 vs card_t5_arity (which names `:typed(None)` and
`:decorated(by=...)` as wrong and gives the attribute replacements verbatim):

    plain  93.2%      arity  94.0%      +0.8
    won  t5-p31 (coincidence), t5-p42, t5-p52
    lost t5-p33, t5-p34

`::call -> ::callees` (p52) and the `:scope`/`:in-scope` shape (p42) did respond to being
told. But p30 and p38 -- the two attribute-vs-pseudo errors -- did NOT move, despite the card
naming them exactly. Telling the model is not enough for these.

The likely cause is overgeneralisation from training, not ignorance: the corpus is full of
LEGITIMATELY parameterised pseudo-classes (`:in-scope(` 198 rows, `:called-by(` 138,
`:calls(` 24), so `:typed(None)` is the natural extension of a pattern the model has seen
hundreds of times. And because the engine never errors on it, nothing has ever contradicted
that generalisation. That is what the arity batch has to undo, and it is why a card line
could not.

## The arity batch failed too, and the verifier's node bound is why

Arm C = arm A's corpus plus 36 arity-contrast pairs (81 rows, 0.5% of 16,009). One new run;
arm A is the control and already existed. 6.5 h.

    eval_arity (12 held-out, py-umwelt)    base e1  8.3%   base e2 25.0%
                                           plus e1 25.0%   plus e2 33.3%
    eval_t5 (118)                          base e2 85.6%   plus e2 82.2%   -3.4

The eval_arity gain is ONE PAIR. Per-pair, the 12 split into three `:decorated` "any-side"
pairs that BOTH arms already answer correctly, and nine attribute-side pairs -- the actual
lesson -- where arm A scores 0/9 and arm C scores 1/9. At 8.3 points per pair on a 12-pair
eval, that is not a measurement. Making the targeted eval this small was my error; the signal
cannot clear its own quantum.

On eval_t5 it is 1 pair won, 5 lost.

### The bounds workaround became a learned artifact

Bare `.fn:typed` is 171-264 nodes on every Python fixture, over verify.py's MAX_NODES=50, so
the any-vs-which contrast could only be expressed class-scoped: `.class#Foo .fn:typed` vs
`.class#Foo .fn[signature="T"]`. The model learned the scope along with the lesson. On t5-p38:

    want   .fn[signature="None"]
    base   .fn:typed(.jump)                                  (bogus argument)
    arity  .class#FnAccessor .fn[signature="None"]            (attribute form, spurious scope)

It DID learn the attribute form -- and prefixed a class from py-pluckit, a TRAINING fixture,
onto an answer about py-variety. A constraint imposed by the verifier leaked into the training
distribution and was learned as part of the pattern. That is a trap for any future batch whose
reference has to be narrowed to satisfy the node bound.

t5-p30 moved partway: `.fn:decorated(decorated_definition...)` -> `.fn:decorated`. The bogus
argument is gone, which is the discarded-argument habit weakening, but it never reaches
`[annotation*="property"]`.

### Where this leaves the 95% target

Nothing trained in this session beats the untrained baseline on eval_t5. Two batches,
~18 h GPU:

    pseudo-d3  (55 pairs)   eval_t5 85.6% -> 83.9%   but +28-33 on non-Python held-out
    arity-a1   (36 pairs)   eval_t5 85.6% -> 82.2%   +1 pair on a 12-pair held-out

The best eval_t5 number produced all session came from a CARD line and no training at all:
9B 93.2% -> 94.0%. Both training batches moved the headline DOWN.

The common cause is dilution: 55 and 36 pairs are 0.3% and 0.5% of the corpus. A batch that
small cannot move a 118-pair Python eval, and both times it cost a few pairs elsewhere. The
honest conclusion is that per-defect contrastive batches are the wrong instrument for moving a
headline number, even though pseudo-d3 proved they DO teach what they encode (+28-33 points,
robust to re-wording, where the baseline was weak).

## The holdout suite inverts the ladder: eval_t5's ranking does not survive unseen repos

323 verified questions, 11 languages, repos that appear in no training fixture. All models got
the same language-neutral card (card_pd.md). Sixteen of my questions began "which file holds
X", which genuinely asks for a FILE -- `.mod:has(.fn#X)` is a defensible answer there and
`.fn#X` is not uniquely right -- so the clean column drops them. My flaw, not the models'.

    model                  eval_t5   holdout(307)   delta
    9b-t5-e2                93.2%        73.3%      -19.9
    4b-t5-e2                90.8%        76.9%      -13.9
    0.8b-base-e2            85.6%        74.3%      -11.3
    0.8b-t5-e1              82.4%        79.5%       -2.9
    0.8b-arity-e2           82.2%        65.8%      -16.4

THE ORDER REVERSES AT THE EXTREMES. On eval_t5 the 9B is best and the 1-epoch 0.8B is worst.
On unseen repos the 1-epoch 0.8B is BEST and the 9B is second-worst. Whatever eval_t5 ranks,
it is not generalisation.

### The second epoch is overfitting, and only the holdout can see it

0.8b-t5-e1 (one epoch) vs 0.8b-base-e2 (two, same corpus):

    eval_t5   82.4% -> 85.6%   +3.2    the headline says epoch 2 is better
    holdout   79.5% -> 74.3%   -5.2    the holdout says it is worse

Every "epoch 2 beats epoch 1" reading in this file is a statement about eval_t5's distribution.

### How the 9B actually fails: it declines the simple answer

named-fn is 119 of 323 pairs and carries the gap -- 0.8B 89/119, 9B 58/119. By emitted shape:

    0.8B    .fn#N 100   .class#N 12   .call#N 5
    9B      .fn#N  58   .class#N 28   .mod:has(.fn#N) 9   .jump#N 5   .mod#N 4

Asked "where is StrPrintf defined" the 9B answers `.class#StrPrintf`; asked for
`.fn#adjustRLimit` it answers `.mod:has(.fn#adjustRLLimit)` -- note the invented second L. It
ALTERED AN IDENTIFIER, which no amount of selector knowledge recovers. The small model answers
`.fn#name` and is right; the large one reaches for structure it was not asked for.

### Caveat stated rather than buried

The 4B and 9B run in NF4 4-bit; the 0.8B runs fp16. That is a real confound for comparing
sizes. It cannot explain a REVERSAL, though: the same quantisation settings produced the 9B's
93.2% win on eval_t5. And the 1-vs-2-epoch comparison is confound-free -- same model, same
quantisation, same corpus, same seed.

### What this costs the session's conclusions

Every training result in this file was scored on eval_t5, and eval_t5 ranks models in an order
the holdout reverses. The two batches that "failed" by moving eval_t5 down (-1.7, -3.4) were
being judged by an instrument that rewards fitting its own fixtures. pseudo-d3's eval_t5 loss
and its +28-33 point gain on non-Python held-out pairs are the same finding seen from two
sides, and the holdout is the side that matters.

## Rewording costs eval_t5 twenty points and the holdout nothing

Every question in both suites was reworded by the 9B BASE model (no adapter): same meaning,
different words, identifiers required to survive verbatim. The identifier guard rejected 6
rewordings that dropped or altered a name -- those would have become unanswerable questions
costing every model a point equally, which reads as a robustness failure but is a broken
question. Rewordings are substantially different, not shuffled: median content-word overlap
0.29 (holdout) and 0.36 (eval_t5), 6 near-copies in 301 and 0 in 113.

    model         eval_t5  ->  reworded          holdout  ->  reworded
    0.8b-t5-e1     82.4%      61.9%   -20.5       79.3%      79.1%   -0.2
    9b-t5-e2       93.2%      73.5%   -19.7       69.7%      65.8%   -3.9

TWENTY POINTS OF eval_t5 IS PHRASING FAMILIARITY. Both models lose ~20 points when the same
questions are asked in different words, against the same fixtures and the same references.
Exact-match falls further still (0.8B 66.1 -> 38.9, 9B 78.8 -> 54.0). The holdout loses 0.2
and 3.9, so its scores are about selectors; eval_t5's are substantially about wording.

The reason is provenance: eval_t5's requests were authored by the same process that wrote the
training pairs, so its phrasings are in-distribution. The holdout's were written fresh in
varied registers, which is why there is little left for a rewording to take away.

### Phrasing and repo-novelty are INDEPENDENT axes

Rewording does NOT flip the ladder -- on reworded eval_t5 the 9B still leads (73.5 vs 61.9),
and on the reworded holdout the 0.8B still leads (65.8 vs 79.1). So:

    changing the WORDS   costs eval_t5 ~20 points, costs the holdout ~0-4, and reorders nothing
    changing the REPOS   reverses the ladder: 9B best on eval_t5 fixtures, 0.8B best elsewhere

Two separate deficiencies, and eval_t5 alone could see neither.

Five of the 301 reworded holdout pairs are at risk because MY `NOT` template interpolated an
article ("functions with no a call anywhere"); on four the model repaired the grammar by
reinterpreting, turning `:not(:has(.call))` into "never invoked", which is `:not(:is-called)`.
Excluding them moves the numbers 79.1 -> 80.4 and 65.8 -> 66.9, so they change nothing
material. eval_t5_rw has zero flagged pairs.

## Adjudication: none of the 13 oracle-sourced pairs agrees with the engine

Every oracle-sourced reference run through the pinned engine and compared with its stored
digest:

    agree 0        disagree 8        engine REFUSES 5

    ERROR  t5-p15 t5-p17 t5-p18 t5-p19 t5-p37   all `[receiver="..."]` -- "no output for query"
    DIFFER t5-p23 (13 vs 15)  t5-p28 (26 vs 33)  t5-p39 (1 vs 0)  t5-p40 (23 vs 39)
           t5-p41 (10 vs 19)  t5-p42 (3 vs 0)    t5-p43 (2 vs 0)  t5-p44 (10 vs 0)

The five ERRORs explain why the oracle exists: it was a workaround for selectors the engine
will not execute, not a convenience. Those pairs ask questions the pinned engine cannot answer
at all, so no model can be right or wrong on them in the engine's terms.

### This overturns my own correction about `:scope`, and the lesson is about evidence

Measured directly, py-variety:

    .fn                           84        .fn:in-scope(.class#Cat)       3  == .class#Cat .fn
    .fn:scope(.class#Cat)          0        .fn:in-scope(.class#Animal)    5
    .fn:scope(.class#Animal)       0        .call:in-scope(.fn#load)       2
    .call:scope(.fn#load)          0

`:scope(X)` with a NAMED argument returns ZERO; with an unnamed one it is vacuous. The earlier
"always 0" claim was RIGHT, and the correction recorded above it -- that a named argument
constrains, citing 3 nodes -- was WRONG. That 3 was t5-p42's stored `reference.count`, and
t5-p42 is oracle-sourced: an oracle number read as an engine measurement.

A stored reference is an engine measurement only when `reference.source == "engine"`. Nothing in
the pair format makes that salient, and I did not check. **card_t5.md:60 should teach
`:in-scope(` after all** -- the opposite of what the earlier entry concluded.

### Retiring the 13 barely moves eval_t5, which is the point

    model            all 118   engine-only 105
    9b-t5-e2          93.2%        94.3%
    4b-t5-e2          90.7%        91.4%
    0.8b-base-e2      85.6%        84.8%
    0.8b-t5-e1        83.1%        84.8%

At most 1.7 points either way. So the dual-instrument problem was never distorting the
headline much -- it was distorting WHICH PAIRS the headline was computed from, and crediting
models for answers the engine disagrees with (six models were credited on t5-p43 for the
descendant form while the engine calls it different). Removing them costs nothing and makes
every remaining number one instrument's opinion.

Worth noting against the 95% target: on 105 engine-scored pairs the 9B reads 94.3%, its best
number anywhere. It is also 73.5% on reworded eval_t5 and 69.7% on unseen repos. The target was
always a property of the instrument.

## What makes the reworded score drop: four hypotheses, three falsified

The 9B loses 26 of 113 pairs when eval_t5 is reworded. Tested causes:

    LENGTH / REGISTER   falsified. Lost pairs are SHORTER (median 6 words vs 8) and LESS
                        formal (0 of 26 capitalised+punctuated, vs 9 of 87 kept).
    SYNONYM RARITY      falsified. Accuracy by training frequency of the rarest word the
                        reword introduced: absent(0) 66.7%, rare 81.1%, mid 72.3%,
                        common 62.5%. Not monotonic; n per band 8-47, so noise.
    SYNONYM PRESENCE    falsified by its own control. 17 of 26 lost pairs had a synonym
                        introduced -- but so did 44 of 80 KEPT pairs. Conditional accuracy
                        72% with a synonym vs 80% without: an 8-point effect, not 20.
    BAD REWORDINGS      partly real but small. 3 of 26 are phantom identifiers, where the
                        reword said "invoke a target" and the model answered `.call#target`,
                        taking a generic noun as a name. Those are my paraphrases failing,
                        not the model.

The training vocabulary IS starkly skewed -- call/calls 10,179 occurrences against 588 for
the whole invoke family, and yield/assign/populate at zero -- but the control shows that skew
does not drive the losses. I nearly recommended a 20-hour corpus rebuild on that correlation.

### What survives: a familiarity bonus with no identified mechanism

The one robust statement is comparative, not causal. eval_t5's requests were authored by the
same process as the training pairs; the holdout's were written fresh. Rewording costs eval_t5
~20 points and the holdout 0.2-3.9. So roughly 20 points of eval_t5 is familiarity with
phrasing rather than selector skill, distributed across the pairs rather than concentrated in
any lexical feature I could find.

CAUTION ON CROSS-SUITE COMPARISON. eval_t5 is tier 5 -- compound `:has`/`:not` selectors --
while 37% of the holdout is named-fn. The suites differ in difficulty as well as provenance, so
their absolute numbers are not comparable; only each suite's original-vs-reworded delta is.

### The lever, stated as an untested hypothesis

Paraphrase diversity in training is the obvious candidate: the corpus carries ~3 phrasings per
pair, all from one authoring process. Generating several model-written paraphrases per pair
(reword.py already does this, with the identifier guard) would multiply phrasings without
adding selectors or leakage risk. But the mechanism I proposed for WHY it would work has just
been falsified, so this is a hypothesis to test, not a recommendation to act on.

The cheap test is one arm, not a corpus rebuild: reword-augment the paraphrases, train the
0.8B once (~6.5 h), and measure against the existing 0.8b-base-e2 on reworded eval_t5 and
reworded holdout. If the delta is flat, phrasing diversity is not the lever either.

## Measurement-hygiene failure: I compared results from two different engines

Three claims above were measured with `ASTCSS_MACROS` unset. The default is
`~/Projects/sitting_duck/src/sql_macros/css_selectors.sql` plus that repo's build -- the LIVE
engine another session has been changing all week -- not the pinned snapshot every verified
pair and every score uses. Measured deliberately, same selectors, same fixture:

    selector                      PINNED (fix127)   main @ff97ef9
    .fn                                 84               84
    .fn:scope(.class#Animal)            84 VACUOUS        0  BROKEN
    .fn:scope(.class)                   84 VACUOUS        0  BROKEN
    .fn:in-scope(.class#Animal)    UNKNOWN pseudo-class    5  works
    .class#Animal .fn                    5                5
    .class#Animal > .fn                  0                0
    .fn:typed / :typed(Zzz)           9 / 9            9 / 9  arg discarded

Live macros on the pinned binary error outright ("Scalar Function with name is_constitu... does
not exist"), so the two are not interchangeable in either direction. `:in-scope` DID NOT EXIST
at the pin and was added later -- yet the training corpus uses `:in-scope(` 198 times, teaching
a selector the pinned evaluation engine rejects.

So the earlier entry "`:scope(X)` always returns 0, measured directly" was measuring MAIN. On
the pinned engine `:scope` is vacuous, not empty. Both are broken; my attribution was not.
The card line should still change to `:in-scope(`, now for a reason that survives scrutiny.

### And the child combinator is NOT broken -- that claim was mine, and wrong

I wrote that `>` is "unfalsifiable on real code" because all 53 holdout child questions were
rejected. It works:

    .class#Animal > block    2        .mod > .class   16        .fn > block   74
    block > .fn             46        .mod > .fn      26

`.class#Animal > .fn` is 0 because a method's AST parent is a `block`, not the
`class_definition` -- correct tree semantics, surprising only if you expect CSS-DOM behaviour.
My 53 questions asked for "methods directly on N" and encoded `.class#N > .fn`, which is not
that; `.class#N > block > .fn` is. The gate rejected them on the lower node bound, and I
misread bounds rejections as vacuity.

### What is left for upstream: two bugs, both confirmed on main @ff97ef9

1. `:scope(X)` returns 0 for every argument while `:in-scope(X)` returns the right answer.
   A dead selector still in the grammar, and the card teaches it.
2. `:typed(X)` and `:decorated(X)` silently DISCARD the argument and return the bare form --
   `:typed(Zzz)` == `:typed`. Contrast `:totally_made_up(x)`, which correctly errors
   "unknown pseudo-class". An arity error exists; it just is not raised for these.

Not bugs, recorded so they are not re-filed: attribute filters inside `:has()` are explicitly
unsupported with a clear error, and `>` is correct as described above.

## The card, the corpus and the engine disagree about scope selection, three ways

Every pseudo-form the training corpus teaches, probed against the PINNED evaluation engine:

    :has 4432  :not 2044  :is-called 181  ::callees 166  :called-by 138  ::callers 117
    :typed 112  :calls 24  :async 15  :decorated 14  :is-referenced 6  :exported 3
        -- all supported --
    :in-scope 198                                           -- UNSUPPORTED: unknown pseudo-class

One form of thirteen, and it is the one 198 training rows teach. So:

    card_t5.md:60  teaches `:scope(X)`      -> pinned engine: VACUOUS (84 nodes = all `.fn`)
    the corpus     teaches `:in-scope(X)`   -> pinned engine: UNKNOWN PSEUDO-CLASS, errors
    the engine     supports neither usefully

Three artefacts, three different answers, and no single one of them is self-consistent with
the others. A model that learns the corpus writes a selector the instrument refuses; one that
follows the card writes a selector that silently matches everything.

### `executes` means two different things and nothing marks which

84 predictions across all runs use `:in-scope(`. 55 "executed" -- and every one of those is on
t5-p42 or t5-p44, both ORACLE-sourced, where `qualify.score` evaluates through oracle.py and
never reaches the engine. The 29 that failed are all engine-scored, erroring with
"unknown pseudo-class". So `executes: True` means "the oracle parsed it" on an oracle pair and
"the engine ran it" on the other 105, and the field does not say which. Any aggregate over
`executes` mixes the two. This is the dual-instrument problem inside a column I had been
reading as uniform.

### Consequence for sitting_duck #184

The fix is being worked on, and it cannot improve any number here until the engine is
RE-PINNED -- the pin is what insulates these measurements, which is why nothing recorded in
this file moved when main went from v1.5.5 to v1.5.6 and back to green. And a re-pin resets
comparability for every score in this file, because `:in-scope` starting to work changes what
198 training rows mean and what the three `:scope` eval pairs measure.

So the sequencing is: land #184, re-pin, re-baseline the ladder, THEN change card_t5.md:60 --
not the other way round. Changing the card against the current pin would make it teach
`:in-scope(`, which this engine rejects outright: worse than the vacuous form it teaches now.

### The scope design, resolved: `:scope` is `::scope` misspelled

Measured, py-variety, pinned engine -- `::scope` is a 1:1 map from each match to its enclosing
scope, cardinality-preserving, node sets differing:

    .fn      84 -> .fn::scope      84        .fn#make_animal   1 -> ::scope  1
    .var     82 -> .var::scope     82        .call#print       5 -> ::scope  5
    .class   19 -> .class::scope   19        (one of those 5 is the module node,
                                              for a top-level print)

So `::scope` and `:in-scope(X)` are INVERSES: one maps nodes to their scopes, the other filters
nodes by scope. Both already work. `:scope(X)` is not a third operation anyone needs -- it is a
spelling that collides with the pseudo-element, which is why CSS precedent makes the
single-colon slip so natural.

Teague's call, filed on #184: normalise bare `:scope` to `::scope`, and make `:scope(X)` with an
argument an arity error naming `:in-scope(X)`. That folds bug 1 into bug 2's fix and leaves no
dead selector, no silent empty set, and no spelling that neither works nor explains itself.

Under that resolution card_t5.md:60 is simply wrong and becomes `:in-scope(.class#Name)` -- the
same edit I had wanted for two previous and wrong reasons, now for a principled one. Still
after the re-pin, not before.

## #184 is fixed on main (94357a8) but UNRELEASED -- do not re-pin yet

Verified against Teague's spelling-is-operation spec, on the local main build (macros and
extension rebuilt 2026-10-03 11:38). Not released, so the pin stays where it is; pinning to an
in-flight state would be worse than the stale pin.

    spec                                              observed on main @94357a8
    ::scope      map match -> enclosing scope         84 nodes, 1:1            MATCHES
    :in-scope(X) filter by containment, narrow        requires an arg; error lists the
                                                      accepted forms           MATCHES
    :is-scope    bare is OK                           84 nodes                 MATCHES
    :is-scope(X) filter by BEING a scope              function/class/module accepted;
                                                      `.call` rejected, deferred to #145
                                                                               PARTIAL
    bare :scope  error                                errors                   MATCHES
    :scope(X)    error naming the alternatives        errors, naming all three MATCHES

The `:scope` message is the model of what these should look like -- it names the operation the
author probably wanted rather than just refusing:

    :scope is not a pseudo-class -- it was ambiguous between three different operations.
    Use ::scope (pseudo-element) to MAP each match to its enclosing scope; :is-scope or
    :is-scope(X) to FILTER to nodes that ARE a scope; or :in-scope(X) to FILTER by the
    scope a node is IN.

And the zero-arity fix names the attribute form, which is exactly the signal the models were
missing: ":typed takes no argument ... To filter on the type itself use the attribute form,
e.g. [signature=\"None\"]". Three of the 9B's eight eval_t5 errors were that confusion, made
unobservable by the silent discard.

### What the re-pin will cost and gain, when it releases

GAIN: all 198 corpus `:in-scope(` rows become valid. Their argument forms are `.fn#NAME` (156)
and `.class#NAME` (42), both of which work on the new build. The corpus and the engine stop
disagreeing.

COST: `card_t5.md:60` stops being merely vacuous and becomes a HARD ERROR -- `:scope(X)` now
raises. So the card edit is no longer optional at re-pin time, it is required, and any model
following the current card fails every scope question outright instead of silently matching
everything.

Also: the 3 oracle-sourced `:scope` eval pairs (t5-p42/43/44) become unexecutable on the new
engine, which settles their fate -- they were already the pairs where zero of 13 oracle
references agreed with the engine.

## Phrasing diversity: confirmed on eval_t5, refuted on the holdout

One arm, one epoch, 15,952 rows against the control's 15,928 -- same 8,326 pairs, same
canonical `nl`, same two paraphrases each, only their SOURCE changed from the original
authoring process to the 4B. 5,214 pairs got model paraphrases; 3,112 failed the identifier
guard or could not produce a second distinct rewrite and kept their originals, so the treatment
is roughly 60%.

                         eval_t5   eval_t5_rw   holdout   holdout_rw
    control 0.8b-t5-e1    83.1%      61.9%       79.3%      79.1%
    arm (4B paraphrases)  89.8%      77.0%       74.6%      67.1%
    delta                 +6.8       +15.0        -4.6      -12.0

    rewording GAP    control: eval_t5 -21.1   holdout -0.2
                     arm:     eval_t5 -12.8   holdout -7.5

On eval_t5 the hypothesis holds and holds well: the rewording gap closes from 21.1 to 12.8
points and the absolute score rises 6.8. That is the largest training gain anything produced
this session, and the first that moved eval_t5 up at all.

On the holdout it is refuted. The arm loses 4.6 points, loses 12.0 reworded, and OPENS a
rewording gap of 7.5 where the control had 0.2. Training on model-written phrasings made the
model newly sensitive to phrasing on the suite that was previously immune to it.

Since the holdout is the better instrument -- that is what the inversion and the rewording
results established -- this intervention is NET NEGATIVE by the measure we trust, while being
the best thing we have ever done to the measure we do not.

### A measured register collapse, offered as mechanism and NOT as cause

                              words med   <=4 words   interrogative   terse opener
    HUMAN train paraphrases       8          4.5%        45.5%            -
    4B train paraphrases          6         19.1%         0.1%           1.0%
    eval_t5 questions             8         14.3%         0.0%            -
    holdout questions (mine)      4         62.2%         0.0%          59.8%

Replacing the human paraphrases wiped out an entire register: 45.5% of them were interrogative
("where is the gather routine that assembles the collections?"), against 0.1% of the 4B's. The
4B is actually TERSER on average, so terseness is not the story; the loss is one specific
dimension of variety, and the corpus went from two registers to one.

That is a correlation, and three correlations have already died today -- length, synonym
rarity, synonym presence. I am not claiming it causes the holdout regression. The clean test is
cheap and not run: reword with a DIFFERENT generator, or mix human and model paraphrases rather
than replacing, and see whether the holdout loss disappears while the eval_t5 gain survives.

### What the session's training record now looks like

    pseudo-d3   55 pairs    eval_t5 -1.7    non-Python held-out +28 to +33
    arity-a1    36 pairs    eval_t5 -3.4    +1 pair on a 12-pair eval
    card line    0 pairs    eval_t5 +0.8    (9B, no training at all)
    reword-para  corpus     eval_t5 +6.8    holdout -4.6, reworded holdout -12.0

Every intervention that moved eval_t5 up moved the holdout down or left it alone, and the one
that moved a held-out measure up (pseudo-d3) moved eval_t5 down. Four for four. On this
evidence eval_t5 and generalisation are not merely different, they are in tension.

## Denial instead of invention: a card granting license has ZERO effect

Three facts explain why no model here has ever declined anything:

    cards granting license to decline     0  -- every card says "Reply with the selector only"
    eval pairs that are unanswerable      0 of 536
    predictions containing refusal words  33 of 23,796  (0.14%)

So invention was never a model defect. The protocol forbade declining and no eval ever
contained a question that should be declined.

New instruments: `card_abstain.md`, which grants `NONE: <what is missing>`, lists what the
language lacks and warns against over-refusing; and `abstain/`, 33 unanswerable requests over
8 categories plus 16 engine-verified answerable controls. Scored as a 2x2, because one number
would hide the trade -- a model that declines everything is perfect on invention and useless.

    run                  ANSWERABLE (16)              UNANSWERABLE (33)
                         right  wrong  over-refused   declined  INVENTED
    0.8B  no license       12      4        0             0        33
    9B    no license       14      2        0             0        33
    0.8B  with license     12      4        0             0        33
    9B    with license     15      1        0             0        33

100% INVENTION IN ALL FOUR CONDITIONS. Not one declination, from either size, with the license
stated explicitly in the system prompt. Config verified: the two cards have different sha256s,
`card_abstain.md` contains the license text, and each run's meta.json records the card it used.

### The inventions are confident and include hallucinated identifiers

    "the biggest class in this codebase"     -> .class#Gargantuan
    "functions longer than fifty lines"      -> .fn:has(while_statement)
    "short helpers, under five lines"        -> .fn:has(continue_statement)
    "any function whose body runs past one screen" -> .fn:has(.call#scroll)

`.class#Gargantuan` is the striking one: asked for the biggest class, the 9B invented a class
named after a synonym for big. `dial_port` and `scroll` are likewise not identifiers in the
fixture. So the failure is not only "answers when it should not" but "fabricates names", and
every one of these executes and returns a plausible-looking node set.

### Card changes do not move trained behaviour -- twice now

This is the second time a card fix produced nothing. The arity card named `:typed(None)` and
`:decorated(by=...)` as wrong and gave the replacements verbatim: +0.8 points, and the two
target errors unmoved. Now an explicit abstention license: zero effect.

Both behaviours are invariants of the corpus -- 100% of training pairs have an answer, so
"always emit a selector" is learned as absolute, and a sentence in the prompt does not
contradict 15,928 rows. Getting denial requires TRAINING on declinations. The suite to measure
it now exists, and the baseline is 0 of 33.

That also means abstention is the one practical axis where a training batch should WORK, for
the reason the earlier batches failed: pseudo-d3 and arity-a1 were 0.3-0.5% nudges to a
behaviour the corpus already covered, whereas declination has no representation in the corpus
at all. A first batch would be teaching something, not outvoting something.

## Register follows the PROMPT, not the model

The plan was nine generators across seven families, on the theory that model diversity buys
register diversity. Measured on 120 queries sampled from eval_t5, the holdout and the corpus:

    generator                      n   wmed terse<=4 long>=12  quest?  imper  Capped  vocab  TTR
    REF human paraphrases      14510      8       5%      17%     45%    90%      0%   2216 0.02
    REF 4B paraphrases (failed) 9012      6      19%       5%      0%     1%      8%   1943 0.04
    REF holdout questions        323      4      62%       0%      0%    54%      7%    318 0.29
    claude:haiku                 120      6      27%       0%      0%    18%      3%    254 0.43
    claude:sonnet                117      6      15%       6%      0%    41%     36%    241 0.36
    tiiny:Qwen3-30B-A3B-Instruct 118      7       5%      12%      0%    10%      0%    253 0.38

Haiku, Sonnet and the device Qwen differ from each other in real ways -- capitalisation 3% vs
36% vs 0%, imperative 18/41/10, terseness 27/15/5. But look at `quest?`: ALL THREE ARE ZERO,
exactly like the 4B whose register collapse cost 12 points on the reworded holdout. The
interrogative register -- 45% of the human paraphrases -- appears in NO model's output.

So nine generators would have bought nine times the cost of the failure already measured.

### The prompt moves it completely. One generator, four targets:

    target        n  wmed terse<=4 long>=12  quest?  imper   example
    question     40     9     10%      10%    100%    75%   "Which functions use a with
                                                             statement without any except
                                                             handlers?"
    terse        40     3    100%       0%      0%     0%   "with block, no except"
    verbose      40    16      0%     100%      0%   100%   "Find all functions that contain
                                                             a with block statement but do
                                                             not contain..."
    imperative   40     8      2%      15%      0%    75%   "Find functions that contain a
                                                             with statement and lack an
                                                             except clause"

100% interrogative on demand, 100% terse at four words or fewer, 100% verbose at twelve or
more. Complete control, from one model, by asking.

### What this changes

Register is a PROMPT axis; model identity is a LEXICAL axis. They are not substitutes, and we
had been shopping on the wrong one. The corpus needs register coverage the human paraphrases
supply (45% interrogative) and every model drops to zero unless told.

So: assign registers deliberately -- question, terse, verbose, imperative, conversational --
and use a handful of generators for lexical variety WITHIN each register, rather than nine
models all writing the same fluent declarative. That is cheaper, controllable, and testable:
the register table is now a pre-flight check, so a batch cannot silently collapse a register
the way the 4B arm did.

Still to measure: whether register-balanced paraphrases actually fix the holdout regression.
This explains the mechanism the earlier section could not identify, but explaining a mechanism
is not demonstrating a fix -- four hypotheses have already died on this question.

## Declination training works, and the capability is in the weights

Arm C: the baseline corpus plus 553 declination rows (+3.4%), licensed per-language cards, one
epoch, seed 18. Baseline for comparison is 0 declinations of 33 under every card at both model
sizes.

                            ANSWERABLE (16)           UNANSWERABLE (33)
                            right wrong over-refused  declined  invented
    before (any model/card)  12-15   1-4      0           0        33
    arm C + licensed card       14     2      0          26         7
    arm C + UNLICENSED card     14     2      0          15        18

0 -> 26 of 33. And 15 of 33 still declined when scored with the UNLICENSED card, which never
mentions declining -- the behaviour survives removing the permission that was present during
training, so it is learned, not prompted. That was the control the confounded two-arm design
could not give, and it is the result that matters: the card alone produced exactly zero
(measured, all four conditions), so the rows did this.

ZERO OVER-REFUSALS on all 16 answerable controls, in both conditions. The failure mode the
controls exist to catch -- a model that declines anything oddly worded -- did not appear.

### Transfer is partial, and the held-out split is what shows it

                  licensed      unlicensed
    TRAINED       22/25  88%    13/25  52%
    HELD-OUT       4/8   50%     2/8   25%

    by category (licensed): size 5/5  judgement 6/6  superlative 3/3  three-step 3/3
                            count 4/5  history 4/4  runtime 1/3  dataflow 0/4

`history` was never trained and transferred completely (4/4) -- "changed in the last week" is
evidently far enough from anything the corpus answers. `dataflow` was never trained and
transferred not at all (0/4): "variables assigned but never read" still draws
`.var:assigned:not(:is-referenced)`, inventing two pseudo-classes. `runtime` WAS trained and
only reached 1/3.

So this is not a keyword rule -- it generalises to one unseen category and to new phrasings of
trained ones -- but neither is it a learned concept of expressibility. Dataflow questions look
answerable to it, and the forms it reaches for are invented vocabulary rather than
near-misses: `.fn:added`, `.var:assigned`.

### Collateral, with a confound the card-only arm will settle

    holdout   79.3% -> 70.3%   -9.0
    eval_t5   83.1% -> 82.2%   -0.9

A 9-point holdout loss is not acceptable as it stands. But arm C differs from the control in
TWO ways -- the declination rows AND the licensed cards -- and the licensed card adds ~10 lines
to every row's system prompt. Arm B (licensed cards, no declination rows, 15,928 rows, 0
declination rows, confirmed at build) separates them. Until it reports, the honest reading is
"declination is learnable at 3.4% of rows, with a 9-point holdout cost of unknown origin".

## The holdout's seed floor is 2.5 points, so every drop this session is real

Four same-config adapters (small-langcard, seeds 18/19/20/21) scored on the holdout:

    seed 18  76.8%     seed 20  74.9%
    seed 19  75.9%     seed 21  74.3%     RANGE 2.5 points   (eval_t5's is 8.3)

The holdout is 3.3x quieter than eval_t5. So the deltas read this session are effects, not
seeds:

    paraphrase arm   -4.6   1.8x the floor
    abstention arm   -9.0   3.6x
    arity arm       -13.5   5.4x

That settles the "are we chasing noise" question in the uncomfortable direction: we are not.
Four interventions, four real losses on the only instrument that tracks generalisation.

### And the measurement that reframes the whole corpus

Those seed adapters are small-langcard: **2,205 rows**, mean 75.5% on the holdout. The control
is t5-langcard: **15,928 rows**, 79.3%.

    7.2x the training data  ->  +3.8 points on unseen repos  (floor 2.5)
    the same comparison     ->  ~50 points on eval_t5 (28-35% vs 82.4%)

eval_t5 says the large corpus is transformative. The holdout says it is worth about one and a
half noise floors. The 50-point gap is tier-5 compound selectors, which t5-langcard trains on
and small-langcard does not, and which eval_t5 is almost entirely made of -- so that gap
measures how well the corpus matches eval_t5, not how well the model reads unfamiliar code.

Caveats held: different corpora (not just different sizes), and the holdout is 37% named-fn so
it may compress real differences. A same-corpus scaling curve (579 / 1,116 / 2,205 rows) is
running to test the first.

### Why this points at the foundation rather than the next experiment

Every intervention that moved eval_t5 up moved the holdout down or flat (4 for 4); the one that
moved a held-out measure up moved eval_t5 down; a 7x corpus buys 1.5 noise floors on unseen
repos; and the untouched 1-epoch 0.8B control beats the 4B and the 9B there. Those four facts
are consistent with one explanation: the corpus and the eval were co-designed, and almost
everything built on top has been optimising the fit between them.

FOUNDATION.md records the nine decisions a v2 should make differently, each with its number.

## Correction: the two suites measure disjoint skills, and "the holdout is the better
## instrument" was overreach

Composition, by the coarse question families a user would recognise:

                                   corpus   eval_t5   holdout
    compound filter (2+ :has/:not)  23.5%    46.7%      3.1%
    call-graph / pseudo              8.0%    21.9%      0.0%
    attribute                       15.8%    19.0%      0.0%
    single filter                   18.9%    11.4%      6.8%
    NAMED LOOKUP (.fn#x)            10.7%     0.0%     74.6%
    combinator                       9.4%     0.0%      0.0%
    named + combinator               8.5%     0.0%      7.4%
    bare class                       5.1%     1.0%      8.0%

eval_t5 is 68.6% compound-filter plus call-graph. The holdout is 74.6% plain `.fn#name`, with
ZERO attribute and ZERO call-graph questions. They barely overlap.

So I have been wrong in a way worth stating plainly: I called the holdout "the better
instrument" repeatedly. It is better at ONE thing -- generalisation to unseen repos and
independent phrasing -- and it badly under-tests composition, which is most of what the
language is for. A suite that is three-quarters named lookups cannot adjudicate compound
selectors, and I used it to do exactly that.

That also deflates the ladder inversion. "The 0.8B beats the 9B on unseen repos" is largely
"the holdout mostly asks the one question every model can answer, and the 9B over-thinks it" --
which matches its measured failure mode: `.class#StrPrintf` for "where is StrPrintf defined",
`.mod:has(.fn#adjustRLLimit)` for `.fn#adjustRLimit`. Real, but far narrower than I implied.

### Where the 9-point abstention drop actually landed

    family          n    control   abstain-arm   delta
    named-fn      119       75%         59%      -16.0
    named-call     53       70%         53%      -17.0
    not            10       80%         60%      -20.0
    named-class    69       87%         86%       -1.4
    bare           26       96%         92%       -3.8
    descendant     24       96%        100%       +4.2
    has            22       64%         73%       +9.1
    ALL           323     79.3%       70.3%       -9.0

The loss is concentrated in NAMED LOOKUPS -- named-fn -16, named-call -17 -- which are 53% of
the suite. `:has` actually IMPROVED (+9.1) and descendants improved. So the declination rows
did not damage compositional skill; they damaged the model's willingness to answer a simple
"where is X defined" with `.fn#X`.

That is a specific, plausible mechanism: 553 rows whose answer is "NONE" taught it that some
questions have no selector, and the questions most likely to be mistaken for those are the
terse ones -- "take me to X", "which file holds X" -- which is exactly the holdout's register.
Over-refusal did not show up on the 16 answerable controls because those are compound and
attribute-shaped, not terse lookups. The controls were the wrong shape to catch it.

**So the abstention batch needs answerable TERSE controls, not just answerable complex ones** --
and that is a corpus-crafting defect in my own suite, of exactly the kind FOUNDATION.md is about.

## `.def#X` already exists, is undocumented, and would dissolve most named-lookup failures

Teague's proposal: "where is X defined" should be `:def#X` rather than forcing a choice between
`.fn#X`, `.class#X`, `.var#X`. There is no `:def` pseudo-class -- but `.def` exists as a
semantic CLASS, and it is exactly the union:

    .def   202 nodes  ==  .fn 84 + .class 19 + .var 82 + .mod 17
    .def#Animal       == .class#Animal   (2 nodes)    .fn#Animal is 0 -- Animal is a class
    .def#make_animal  == .fn#make_animal (1 node)

So the capability is already there and `card_t5.md` never mentions it. The card lists `.fn
.func .method .class .mod .var .call ...` and omits the one class that makes a name lookup
answerable without first knowing what kind of thing the name is.

### Why that matters more than it sounds

Of the holdout's named-lookup FAILURES, almost all are right name, wrong class:

    model          named-lookup failures   RIGHT NAME, wrong class   wrong name   no #name
    9B                      92                     87 (95%)              3           2
    0.8B control            55                     38 (69%)             16           1
    abstention arm          84                     73 (87%)              6           5

The 9B gets the identifier right and the class wrong in 95% of its failures: `.class#StrPrintf`
for a function, `.mod#StrAppend` for a function. It is not failing to find the name -- it is
being forced to guess a kind the English never specified, and being marked wrong for guessing.

`.def#X` makes those questions answerable as asked. On the holdout that is up to 87 of the 9B's
92 named-lookup failures, i.e. roughly 27 points of a 323-pair suite, from documenting one class
that already works.

### What this says about the foundation argument

The holdout is 74.6% named lookups, and ~90% of its failures are a class-guessing artefact of
the card's vocabulary rather than a reasoning failure. So:

  - the "ladder inversion" is further deflated: much of the 9B's holdout deficit is this one
    artefact, and the 0.8B wins partly by guessing `.fn` more often, which the suite rewards
    because `named-fn` is its largest family
  - the corpus never teaches `.def` (0 of 8,326 pairs use it, since the card does not list it)
  - my holdout questions ("where is X defined", "take me to X") are themselves under-specified
    against the documented vocabulary -- a corpus-crafting defect in MY instrument, again

The honest version: a chunk of what this session measured as generalisation failure is a
vocabulary gap in the card, inherited by the corpus, and amplified by an eval I wrote to ask
exactly the question that gap makes ambiguous.

## The card documents 25 classes; the engine supports at least 22 more

Teague asked whether other constructs are missing. Enumerated properly this time, from
`ast_type_map('python')` -- the extension's own taxonomy, 15 `kind` values -- then probed
against the engine rather than guessed:

    VALID, and absent from card_t5.md          nodes on py-variety
      .name / .identifier                       693 / 650
      .block                                    306
      .def / .definition                        202   (== .fn + .class + .var + .mod)
      .access                                   166
      .operator / .op                           139
      .literal                                  137
      .statement / .stmt                        114
      .flow                                      89
      .type                                      82
      .qualified                                 38
      .conditional                               22
      .external                                  20
      .struct                                    19
      .list                                      13
      .pattern                                    9
      .error                                      8
      .transform                                  4
      .syntax                                     2

The card teaches 25 classes and omits these. `.name`/`.identifier` is the largest class in the
language (693 nodes, more than `.call`) and no pair in the corpus uses it, because nothing told
the authors it existed. `.def` is the one that makes "where is X defined" answerable as asked.

### A FOURTH silent-acceptance bug: unknown classes return 0 nodes

    .zzzznotathing   0 nodes, no error
    .frobnicate      0 nodes, no error

So an invented or mistyped class is indistinguishable from a correct selector that matches
nothing. This is the same failure as `:scope(X)` (vacuous), `:typed(X)` (argument discarded)
and `:decorated(X)` -- three of which sitting_duck #184 has now fixed -- but in the CLASS
resolution path rather than the pseudo-class path, so #184's fix does not cover it.

It also explains why the models' inventions looked plausible all session. `.fn:added`,
`.var:assigned` and the rest executed and returned a clean empty set; nothing in the pipeline
could tell "there is no such thing" from "there is nothing of that kind here". A model trained
against this engine gets no corrective signal for inventing vocabulary.

### What this does to the foundation argument

The card is not merely narrow, it is 47% of the vocabulary. The corpus inherited that gap
(0 of 8,326 pairs use `.def`, `.name`, `.block`, `.access`, `.literal`, `.statement`, `.flow`,
`.type`), and the evals inherited it from the corpus. So "we built it on the wrong content" is
measurable: we taught a subset of the language, tested the same subset, and the questions users
actually ask -- "where is X defined", "what references X" -- land squarely in the half we never
documented.

That is a better reason to rebuild than any of the accuracy deltas, because it is not a tuning
problem. No amount of training on the documented half discovers `.def`.

## The 9-point abstention drop splits in half: the CARD cost 5 points, the rows cost 4

Three arms, one epoch each, seed 18, same base:

    arm                                holdout   eval_t5   declined (of 33)
    A  control, original cards          79.3%     83.1%       0
    B  LICENSED cards, no new rows      74.3%     87.3%       0
    C  licensed cards + 553 declines    70.3%     82.2%      26

    B - A  isolates the CARD:   holdout -5.0   eval_t5 +4.2   declined +0
    C - B  isolates the ROWS:   holdout -4.0   eval_t5 -5.1   declined +26

Both halves clear the 2.5-point holdout noise floor, so both are real.

### Two things worth separating

**The card is inert for TEACHING and expensive for TRAINING.** Arm B declined 0 of 33 -- the
licence text, present in every training row's system prompt, produced not one declination. That
is the third independent measurement of the card's inertness (inference on an untrained model:
0/33; the arity card: 2 target errors unmoved; now training: 0/33). So arm C's 26/33 is
attributable to the 553 rows alone, which is the clean attribution the two-arm design could not
give.

But the same inert text cost **5 points of holdout accuracy** -- more than the rows did. Ten
lines added to 15,928 system prompts, teaching nothing, and the single largest holdout
regression of the three arms. Card text is not neutral scaffolding; it is a training-time
intervention with a measurable price.

**And it reproduces the session's trade exactly.** The card alone: eval_t5 +4.2, holdout -5.0.
Every lever found this session moves the two in opposite directions, including one that was
supposed to be a no-op control.

### Where that leaves the abstention work

Declination is learnable and the capability lands in the weights (26/33 licensed, 15/33 under a
card that never mentions declining). The cost is 4 points of holdout, concentrated entirely in
named lookups (named-fn -16, named-call -17) while `:has` improved -- so the rows taught
"some questions have no selector" and the terse questions got caught in it.

Two fixes follow, neither tried: a much terser licence line (the 5-point card cost is pure
overhead given it teaches nothing), and answerable TERSE controls in the abstain suite, which
my compound-shaped controls were the wrong shape to catch.

## CORRECTION: data scale DOES buy generalisation. The curve is steep, not flat.

I predicted this would come back flat and said so. It did not. Same corpus, same config
(`--system none`), same model (9B), three fractions, scored on the holdout:

      579 rows   59.1%
    1,116 rows   68.1%   +9.0
    2,205 rows   75.5%   +7.4

Still climbing at the top, at ~7-9 points per doubling. Nothing about this says more data
is worthless.

### What I got wrong, and what the earlier comparison actually showed

Earlier I wrote "7.2x the training data -> +3.8 points on unseen repos", comparing the
2,205-row small-langcard seeds (75.5% mean) against the 15,928-row t5-langcard control (79.3%).
That comparison crosses TWO confounds: different model (9B vs 0.8B) and different prompting
(no system card vs per-language cards). It is not a scaling measurement and I presented it as
one.

The clean curve above is a scaling measurement, and it says scale works. Whether it flattens
between 2,205 and 15,928 rows is simply UNTESTED: the only 15,928-row point we have is a
different model under a different config.

### What would actually test it

t5-langcard at `--train-frac` 0.15 / 0.5 / 1.0, one model, one config -- three training runs,
~9.5 h. That is the measurement that would say whether the corpus is past its knee. Until it
exists, "the corpus is too big to help" is my speculation, not a finding.

### What survives, and why the rebuild case is now narrower but not weaker

Unchanged by this: the card documents ~53% of the vocabulary; `.def` and `.name`/`.identifier`
(the largest class in the language) appear in 0 of 8,326 pairs; 95% of the 9B's named-lookup
failures are right-name-wrong-class, an artefact of that gap; the two suites measure disjoint
skills; and the engine cannot distinguish an invented class from an empty result (#188).

So the rebuild argument is about CONTENT COVERAGE, not corpus size -- and this curve makes that
sharper rather than softer. Scale evidently converts rows into generalisation at a good rate.
We have been spending that rate on half a language.

## The full vocabulary audit: 35 constructs missing from a card that documents ~40

Probed every construct category against the pinned engine. Unknown ATTRIBUTES and
PSEUDO-ELEMENTS error cleanly (`.fn[zzznotathing]`, `.fn::zzznotathing`), and unknown
pseudo-classes error too, so only the CLASS path is silent (#188) -- which makes the rest of
this audit reliable.

### Classes — 22 missing (listed earlier)

`.def`/`.definition` 202, `.name`/`.identifier` 693/650, `.block` 306, `.access` 166,
`.operator`/`.op` 139, `.literal` 137, `.statement`/`.stmt` 114, `.flow` 89, `.type` 82,
`.qualified` 38, `.conditional` 22, `.external` 20, `.struct` 19, `.list` 13, `.pattern` 9,
`.error` 8, `.transform` 4, `.syntax` 2.

### Pseudo-classes — 5 missing

    .fn:first-child      23      .fn:empty        5
    .fn:last-child       28      .fn:is-scope    84
    .fn:nth-child(1)     23      (:only-child ERRORS -- not supported)

Position and structure are expressible. I had assumed they were not, and built an abstention
category on that assumption before catching it.

### Pseudo-elements — 2 missing

    .fn::scope     84        .call::parent    84      (::children ::siblings ::body ::name
                                                       all ERROR -- not supported)

`::parent` is new: it maps each match to its syntactic parent, as `::scope` maps to its
enclosing scope.

### Attributes — 6 missing, and two of them are whole capabilities

    [language="python"]                  84    filter by source language
    [type="function_definition"]         74    exact node type as an ATTRIBUTE
    [semantic="DEFINITION_FUNCTION"]    159    the 44-value semantic taxonomy as a filter
    [semantic="NAME_IDENTIFIER"]        650
    [qualified*="Animal"]                 5    QUALIFIED name matching
    [modifier="async"]                    2    async / static / etc.
    [peek*="def "]                       74    MATCHES THE SOURCE TEXT

`[peek*="..."]` is a text search inside a structural selector -- grep and AST query in one
expression -- and nothing in the project uses or documents it. `[semantic=...]` exposes the
entire taxonomy `ast_type_map` publishes (44 values) as a selector dimension. `[qualified*=]`
answers "methods of Animal" without a combinator at all, which matters because combinators are
capped at two steps.

Note the card teaches bare node types as SELECTORS (`function_definition`) but not
`[type="function_definition"]` as a filter, so `.call[type="..."]` compositions were unreachable.

### Sum

    documented in card_t5.md   ~40 constructs
    missing and working         35  (22 classes, 5 pseudo-classes, 2 pseudo-elements,
                                     6 attributes)

The card is roughly half the language. The corpus inherited exactly that half -- 0 of 8,326
pairs use any of the 35 -- and both evals were written from the corpus. The practically useful
questions land in the missing half: "where is X defined" (`.def#X`), "what references X"
(`.name#X`), "find the text TODO inside a function" (`[peek*=]`), "methods of Animal"
(`[qualified*=]`), "the async ones" (`[modifier="async"]`).

## Pre-registration for the vocab-v2 arms: three things I should have checked before predicting

Written 2026-10-04 21:20, while B' trains and ~2.5 h before either arm lands, so this reads as a
prediction and not as an explanation. `workspace/vocab_ab.sh` carries the committed claim:

> C' should RAISE the holdout ... because the holdout is 74.6% named lookups and 95% of the 9B's
> failures there are right-name-wrong-class ... If the holdout does not move, the mechanism is
> wrong and I have misread it.

Checking the instrument while it still mattered found that commitment was stated too strongly.

**1. The references do reproduce (`workspace/refcheck.py`).** Scoring is digest equality against a
`reference.sha256` stored in the pair file, and three of the four suites deciding tonight
(`holdout`, `holdout_rw`, `eval_vocab`) carry **no `reference.source` key at all** — so the
provenance rule from the `:scope` correction ("never read a stored reference without checking its
source") cannot be applied to them by reading. It has to be re-measured. Re-executing every
engine-sourced reference on the pinned engine:

```
eval_vocab   n=113  match 113      holdout      n=323  match 323
eval_t5      n=105  match 105      holdout_rw   n=301  match 301
```

842/842, zero mismatches, zero errors; the 13 oracle-sourced eval_t5 pairs are skipped, not
judged. The result cache cannot hide engine drift either: `_engine_key` hashes the **contents** of
the CLI, the extension and the macros file (`verify.py:246`), so the measurement I ran with
`ASTCSS_MACROS` unset landed in a different cache namespace rather than contaminating this one.
The instrument is sound. **These three suites should still be stamped `source: "engine"`** — not
for tonight, but so the next session can read what I had to re-execute.

**2. The 95% was the 9B. On the 0.8B being trained it is 58%.** Arm A's stored holdout rows
(`runs/ho-0.8b-t5-e1/scores.jsonl`, adapter `t5-langcard/epoch1`, card `card_pd.md`):

```
holdout n=323  correct 256 (79.3%)  fail 67
   RIGHT NAME, wrong class   39   58.2% of failures
   wrong name                16   23.9%
   no name in reference      11   16.4%
   dropped the name           1    1.5%
suite: 265/323 (82.0%) pairs carry a #name
```

Right-name-wrong-class is still the dominant failure mode, so `.def#X` is aimed at the right
target — but the arithmetic ceiling is 39 of 323 pairs, **+12.1 points**, not whatever "95% of
failures" implied. I quoted a number measured on one model as a property of another.

**3. The dose is 0.36%.** Of 491 vocabulary pairs, `--cap-template 8` and the val split leave the
flagship construct at **59 `.def#` rows in 16,288** train rows:

```
train  .name# 64   .def# 59   ::scope 41   ::parent 39   [qualified 23   [peek 12
val    .def# 12    .name# 7   ::parent 6   ::scope 3     [qualified 2
```

**What this does to the commitment.** I wrote that a flat holdout proves the mechanism wrong. It
does not: a null result now has three live explanations — the mechanism is wrong, the dose is too
small at 0.36%, or the instrument scores a correct `.def#X` answer as wrong because the reference
is written `.fn#X`. The third is measurable without the GPU and is running
(`workspace/def_ceiling.py`); the second is not separable from this run at all. **The honest
reading is that this experiment can disconfirm the mechanism only if the ceiling test says a
`.def#X` answer scores correct, and even then a null is confounded with dose.** The commitment
stands as written — I am not deleting it — but it was written without checking either number.

**4. Two of the four columns had no baseline.** Arm A has `holdout` (79.3%) and `holdout_rw`
(79.1%) but had never been scored on `eval_vocab` or on the full 118-pair `eval_t5`, so B'−A was
not computable there. Queued as `astcss-arm-a.service`, which polls until the vocab arms release
the GPU rather than competing with them: `t5-langcard/epoch1` on `eval_vocab` with `card_pd.md`
(A's own eval card, so the difference is the treatment and not an eval-prompt change) and on
`eval_t5` with both `card_pd.md` and `card_t5.md`, so the two conventions are visible instead of
assumed equal. A is expected to score near zero on `eval_vocab`: it was neither taught the
constructs nor given a card that documents them, and in arm A those two causes are inseparable.

### The `.def#X` ceiling: +6.2 points, and two flaws in my own test on the way there

`workspace/def_ceiling.py` executes `.def#X` for every holdout pair carrying a single `#name` and
compares the digest to the stored reference — the question being whether a model that learns the
*intended* construct would even be scored correct. Three passes, because the first two were wrong:

**Pass 1, all 265 single-named pairs.** Gain 33, loss 73, apparent net **−12.4 points** — which
would have meant teaching `.def#X` is harmful under this instrument. The breakdown refuted it:

```
   ref class         same different   zero   n
   fn                 110         9      0  119
   class               59        34      0   93
   call                 0        14     39   53
```

All 53 `.call#X` pairs diverge, and **that is `.def` answering correctly.** `.call#count` asks
where `count` is *called*; `.def#count` returning nothing is the right answer to a different
question. I substituted on the selector's shape and ignored what the pair was asking.

**Pass 2, the 212 `fn`/`class` pairs.** Net −0.9. Still wrong: it keeps descendant selectors like
`.class#Chemv2Tests .fn` ("the functions inside class X", ref n=10, `.def` n=1), where the
substitution is just as mis-aimed.

**Pass 3, the 188 bare `.fn#X` / `.class#X` lookups** — the only pairs that actually ask "where is
X defined":

```
  A FAILS   n= 39   .def#X same node set 33   different  6
  A PASSES  n=149   .def#X same node set 136  different 13
  gain +33 (+10.2 pts)   loss -13 (-4.0 pts)   NET +6.2 points on 323
  .fn#X    -> .def#X same node set 110/119 (92.4%)
  .class#X -> .def#X same node set  59/69  (85.5%)
```

So the mechanism's ceiling is **real and positive: +6.2 points**, not the −12.4 my first pass
implied. All 13 losses are pairs A currently passes, and all 10 bare-`.class` divergences are
`.def` matching *more* than the reference — `.def#Compound` returns 8 nodes where
`.class#Compound` returns 1, because `.def` also finds the variable, the method and the
constructor of that name. Defensible semantics, scored wrong.

**What this does to tonight's reading.** The prediction's direction survives, with a quantified
ceiling: C' should raise the holdout by somewhere in `0 .. +6.2` points, scaled by how often a
0.8B trained on **59 `.def#` rows in 16,288** actually emits the construct. The holdout noise
floor is **2.5 points**, so a true effect of a third of the ceiling is *indistinguishable from
noise* — the experiment is underpowered for its own mechanism, and that was fixed at dataset-build
time, not tonight. **A flat holdout will therefore not disconfirm the mechanism**, contrary to what
I committed in `vocab_ab.sh`; only a *drop* beyond −2.5 would, and the ceiling test says the
arithmetic cannot produce one from `.def` substitution alone.

The transferable error is the one I keep making in a new costume: pass 1 took the mean over a
population I had not checked was homogeneous. The `.call` pairs were 20% of the sample and had the
opposite sign for a principled reason — the same shape as reading the watchdog's 0.25 models/firing
as one mechanism when 81% of the firings were a different event, and as quoting the 9B's 95% as a
property of the 0.8B. **Partition before averaging.**

### eval_t5's 13 oracle pairs are biased against the card_v2 arms

The 13 oracle-sourced eval_t5 pairs score predictions through `oracle.parse`, which predates
`card_v2`. Tested directly:

```
  .def#foo  .name#foo  .fn::scope  .fn:in-scope(.class#C)  [peek*=]  [qualified*=]  .block
  .literal  .access                                         -> parsed
  ::scope (bare)   .fn::parent   .fn:is-scope                -> REFUSED (None)
```

So a B'/C' prediction using `::parent` or `:is-scope` — both of which `card_v2` teaches — is scored
`executes: False` on those pairs for a reason that has nothing to do with the engine, which runs
them fine. The bias is bounded (13 of 118 pairs, and only where the model reaches for those two
constructs) but it is one-directional: it can only hurt the arms that were taught the new
vocabulary. **Report eval_t5 as the 105 engine-sourced pairs, with the 13 shown separately rather
than folded in.** This is the same dual-instrument hazard as the `:scope` correction, now with a
measured list of which spellings the two instruments disagree about.

## Vocab-v2 verdict: the mechanism is confirmed, the card taxes again, and a new brittleness

Three arms, 0.8B, seed 18, 1 epoch. A = `t5-langcard/epoch1` + `card_pd.md` (original cards and
corpus); B' = `card_v2` cards, **identical 15,928 rows**; C' = `card_v2` + 491 vocabulary pairs
(16,288 rows). Scored on the pinned engine; all 842 references re-verified beforehand.

```
suite                     A       B'       C'      B'-A    C'-B'
holdout (323)         79.3%    74.0%    77.1%      -5.3     +3.1
holdout_rw (301)      79.1%    70.8%    69.4%      -8.3     -1.3
eval_vocab (113)      10.6%    21.2%    85.0%     +10.6    +63.7
eval_t5 (118)         83.1%    81.4%    80.5%      -1.7     -0.8
eval_t5 (105 engine)  84.8%    81.0%    79.0%      -3.8     -1.9
```
Noise floors: holdout **2.5**, eval_t5 **8.3**. A's eval card made no difference on eval_t5
(`card_pd` 83.1% == `card_t5` 83.1%), so B'−A there is not an eval-prompt artifact.

**1. The predicted mechanism is confirmed, and the attribution is clean.** C'−B' on the holdout is
**+3.1 points**, above the 2.5-point floor and the only arm all session to raise it. The +10 net
pairs decompose as **+9 from pairs where C' emitted `.def#` and +1 from everything else**:

```
   where C' used .def#     B' -> C'    n          .def# emitted on 24 holdout pairs
     wrong -> right              9                22 of 24 scored correct (91.7%)
     right -> right             13                predicted safe-substitute rate: 92.4%
     wrong -> wrong              2
     right -> wrong              0   <- no losses
```

Zero right→wrong flips, and the realized 91.7% hit rate lands on the 92.4% the ceiling test
predicted for `.fn#X`. +9 pairs is +2.8 points against a +6.2 ceiling — **45% of the ceiling, from
59 `.def#` training rows (0.36%)**. The pre-registered mechanism was right in direction, in
magnitude-relative-to-ceiling, and in the specific construct doing the work.

**2. The card taxes again — third replication.** B' changed *only* the card text and lost 5.3
holdout points, 8.3 reworded, 3.8 on eval_t5's engine pairs, while buying 10.6 points of
eval_vocab. The pairs bought 63.7 on the same suite. Card text has now cost ~5 holdout points in
three independent arms (pseudo-d1, abstention, vocab-v2) and has never taught more than a fraction
of what pairs teach. **Stop paying for vocabulary in card lines.**

**3. New: the v2 arms are brittle to phrasing, and A is not.** Paired on the same 301 ids, original
wording vs the same query reworded:

```
arm        n   original   reworded     delta   flips wrong->right / right->wrong
A        301      78.1%      79.1%      +1.0        28 / 25
B'       301      72.4%      70.8%      -1.7        26 / 31
C'       301      75.7%      69.4%      -6.3        18 / 37
```

A is phrasing-robust to within noise; C' loses 6.3 points, lopsidedly (18 vs 37). This is not `.def`
over-firing — `.def#` scored **29/30** on reworded queries. Of C's 37 regressions, **23 are shared
with B'**, so the brittleness is mostly the card and the v2 training, with ~14 pairs specific to the
vocabulary rows. The failure mode is reversion to raw node types and invention:

```
  ref .class#DescriptorTests        orig .class#DescriptorTests   rw class_definition#DescriptorTests
  ref .call#concat                  orig .call#concat             rw .fn#concat::callers
  ref .call#setBackgroundColor      orig .call#setBackgroundColor rw method_definition:has(.call#setBackgroundColor)
```

`::callers` does not exist. This is the invention-under-paraphrase that the practical-usefulness
goal names directly, and it is *created* by this training round rather than inherited.

**Caveat on the instrument:** every `holdout_rw` query carries the same `reword_model` hash — the
suite is one model's paraphrase style, so "robust to rewording" currently means robust to that one
voice. Mixing reword models is the fix and is untested.

**4. Net position.** C' vs A on the holdout is −2.2, inside the noise floor. So the round roughly
breaks even on the existing suite while taking eval_vocab from 10.6% to 85.0% — the model can now
express `.def`, `.name`, `::scope`, `::parent`, `[peek]`, `[qualified]` at no measurable cost to
what it already did. The two bills are the card tax (−5.3, avoidable) and the phrasing brittleness
(−6.3 paired, newly introduced).

### Correction: `::callers` exists, the model did not invent it, and nothing was invented at all

I reported `.fn#concat::callers` as an invented construct and used it as evidence of
"invention under paraphrase". Teague asked whether `::callers` should exist. It does.

```
known_pseudo_element_names: parent, parent-definition, scope,
                            next-sibling, prev-sibling, previous-sibling,
                            callers, callees          (pinned macros, line 968)

.fn::callers        n=4     .fn#execute::callers  n=4
.fn::callees        n=41    .fn#execute::callees  n=2
```

`.fn#concat::callers` returned 0 only because its **left side is empty** — `.fn#concat` is n=0,
since `concat` is a library method with no definition in that fixture. The selector was
well-formed and the operation was the right one for "which functions call concat". Worse for my
claim: **the training corpus contains 155 rows using `::callers`** — the model learned it from our
own data. I called our own corpus a hallucination.

The strict check kills the invention story entirely: **every prediction executed.** Across all six
arm/phrasing combinations, 2 of 1,872 predictions were rejected by the engine, and of C's 37
rewording regressions, **37 of 37 were valid astcss that selected the wrong nodes** — none
malformed. So the brittleness is real but it is *not* a syntax-hallucination problem: under
paraphrase these models switch to a different **valid** selector. `class_definition#X` (n=0,
accepted, selects nothing) is the characteristic shape. That is a better-behaved failure than I
described, and it means the fix is discrimination training, not a denial licence.

**The card gap is real, though:** `card_v2` documents 2 of the engine's 8 pseudo-elements
(`::scope`, `::parent`) and omits `::callers`, `::callees`, `::parent-definition`,
`::next-sibling`, `::prev-sibling`. Given the card tax, the right response is *not* five more card
lines — the corpus already teaches `::callers` 155 times with no card support and the model used it
correctly-formed.

### Sixth silent-acceptance defect: `:calls()` / `:called-by()` discard a selector argument

The grammar is a **bare name**, and that form is correct:

```
.fn:calls(execute)                 n=4    <- matches the stored reference exactly
.fn:calls(zzzDefinitelyNotAFunction) n=0
.fn:calls(EXECUTEXX)               n=0
```

Pass a *selector* instead, or nothing at all, and the argument is silently dropped:

```
.fn:calls(.fn#execute)   n=38      .call:called-by(load)        n=2
.fn:calls(.class#Cat)    n=38      .call:called-by(.fn#load)    n=79
.fn:calls(.literal)      n=38      .call:called-by(.class)      n=79
.fn:calls(*)             n=38
.fn:calls()              n=38      <- no argument, same answer
```

38 and 79 are the unfiltered sets ("functions that call anything", "calls sited in any function").
This is the #184 / #188 family — a wrong argument *type* accepted and discarded rather than
refused — on the call-graph pseudo-classes, which neither issue covers. **My first probe of this
drew the wrong conclusion** because I passed `:calls(.fn#X)` and concluded the argument was always
ignored; the bare-name form disproves that. Test the grammar the corpus actually uses before
calling an engine broken.

**Also retracted:** the pending note that "198 corpus rows teach `:in-scope(`, unsupported by the
pinned engine". The 198 rows are real (`workspace/trainset-t5/pairs.jsonl`) but `:in-scope(` **works
on this engine** — `.fn:in-scope(.class#Cat)` = 3, identical to `.class#Cat .fn`. Nothing to fix,
and the re-pin does not need to resolve it.

## Probing the latest sitting_duck (048bd59, 2026-10-05)

Snapshotted the peer session's build into `workspace/engine/sd-20261005-048bd59` rather than
executing out of `~/Projects/sitting_duck`, which another session owns and had rebuilt 13 minutes
earlier — nothing in that repo was touched, the macros came out by `git show HEAD:...` (that file
is clean), and `PROVENANCE.md` records that the tree was **dirty** when the binary was built, so
every number here is provisional. `v1.15.4-4-g048bd59-dirty`, branch
`feat/188-call-sites-and-alias-table`, ahead of main (5b38e8f), contains the #184 fix 94357a8.

**#184 is fixed, exactly to the spelling=operation spec** — the macro carries the rationale as a
comment:

```
.fn:scope(.class#Cat)   ERROR: :scope is not a pseudo-class     .fn::scope             n=84
.fn:scope               ERROR: :scope is not a pseudo-class     .fn:is-scope           n=84
.fn:is-scope(.class#Cat)  n=0                                   .fn:in-scope(.class#Cat) n=3 == .class#Cat .fn
```

**The `:typed`/`:decorated` half is fixed too**, and more strictly than I expected — the argument
is now refused outright rather than accepted:

```
.fn:typed       n=9     .fn:typed(int) / (zzzNope) / (.class)  ERROR: :typed takes no argument
.fn:decorated   n=2     .fn:decorated(staticmethod)            ERROR: :decorated takes no argument
```

Unknown pseudo-classes and pseudo-elements now error as well. **Zero corpus rows use `:scope(`,
`:typed(` or `:decorated(`**, so this fix costs the corpus nothing.

**Still live on the latest build — the defect found today:**

```
.fn:calls(execute)        n=4     <- bare name, correct
.fn:calls(.fn#execute)    n=38    .call:called-by(load)       n=2    <- bare name, correct
.fn:calls(.class#Cat)     n=38    .call:called-by(.fn#load)   n=79
.fn:calls(*)              n=38    .call:called-by(.class)     n=79
.fn:calls()               n=38    <- no argument at all
```

Identical to the pinned engine. A selector or empty argument where a **name** is expected is still
silently dropped, yielding the unfiltered set. Neither #184 nor #188 covers it.

**#188 is still live, and worse than I filed it.** I reported "unknown semantic class returns 0
nodes, no error". The compound form is the dangerous one:

```
.zzzNotARealClass        n=0     <- as filed
.fn.zzzNotARealClass     n=84    == .fn   <- the unknown class is dropped, not applied
```

So an unknown class in a compound selector does not merely return nothing — it **silently
disappears and the selector returns everything the rest of it matches**. A typo widens the result
set instead of emptying it.

**Re-pin hazard: the call-graph pseudo-elements changed results.** `.fn::callers` 4 → **24**,
`.fn::callees` 41 → **79** between the pin and 048bd59, and the new engine adds `::call-sites`
(n=38). The training corpus carries `::callees` 220 rows, `:is-called` 181, `::callers` 155,
`:called-by(` 138 — so a re-pin touches roughly 700 training rows and ~47 eval pairs. Training rows
teach selector *strings* and survive a semantics change; **eval references do not**, and the
full 842-reference re-verification against 048bd59 is running to price that exactly.

### Re-pin price: 6 of 554 eval pairs (1.1%)

All 842 engine-sourced references re-executed against 048bd59:

```
eval_vocab  n=113  match 113              holdout     n=323  match 318  MISMATCH 5
eval_t5     n=105  match 104  MISMATCH 1  holdout_rw  n=301  match 296  MISMATCH 5
```

Six distinct pairs move (holdout and holdout_rw share five, being the same pairs reworded):

```
ho-0013  .call                  ho-bash-plinking    39 -> 362   "every invocation"
ho-0004  .fn:has(.call)         ho-bash-plinking     1 ->   3
ho-0005  .fn:not(:has(.call))   ho-bash-plinking     2 ->   0
ho-0367  .fn:not(:has(.call))   ho-rust-fabric      15 ->  16
ho-0060  .import                ho-c-graphqlparser  41 ->  24   "show the includes"
t5-p55   .fn#level2::callees                          5 ->   1
```

Paired on the same fixture, pinned vs 048bd59:

```
ho-bash-plinking    .call  39 -> 362    .access 597 -> 920    .fn 3 -> 3    .member 493 -> 493
```

So bash **commands** are now classified as calls — defensible (in bash every command is an
invocation) and almost certainly intentional from the alias-table work; `.fn` and `.member` are
untouched, so this is not a broad reclassification. Three of the six mismatches are that one change
and its `:has()` consequences. The C `.import` **narrowing** (41 → 24 `#include`s) and the
`::callees` narrowing (5 → 1) are the two I cannot attribute to an obvious intent and would ask
about before re-pinning.

**The named forms are stable.** `.fn#execute::callers` = 4 on both engines; it is the *bare*
`.fn::callers` that moved (4 → 24) and `.fn::callees` (41 → 79). Eval pairs overwhelmingly use the
named form, which is why 220 corpus rows of `::callees` cost only one eval pair.

**Verdict: re-pinning is cheap and worth doing** — it buys the whole #184 fix (which costs the
corpus zero rows, since nothing uses `:scope(`, `:typed(` or `:decorated(`) for the price of
re-verifying six references. It should be done against a *released* build, not this dirty feature
branch. The two defects that survive to the latest build — the `:calls()`/`:called-by()` argument
type, and #188's compound form where `.fn.zzzUnknown` returns all of `.fn` — are unaffected by the
re-pin either way.

### Correction: the two "unattributed" changes are bug fixes, and our pinned references are the wrong ones

I said I would ask the peer about the `.import` narrowing and the `::callees` narrowing before
re-pinning. Both are answerable from here, and both are the engine becoming *more* correct.

**`.import` was double-counting an import's own child nodes.** Per node type, pinned vs 048bd59:

```
ho-js-amongus     .import  40 -> 10     import_statement 10  import_clause 10
                                        import_specifier 10  named_imports 10   (10+10+10+10 = 40)
ho-c-graphqlparser .import 41 -> 24     preproc_include  24  system_lib_string 17   (24+17 = 41)
py-variety        .import  31 -> 20     import_statement  7  import_from_statement 13  (7+13 = 20)
ho-rust-fabric    .import  27 -> 27     unchanged
```

The pinned engine matched the `import_statement` **and** its `import_clause`, `import_specifier`
and `named_imports` children as four separate `.import` nodes; the C case counted the include
*path string* as an import. Latest returns one node per import statement. So holdout `ho-0060`
("show the includes", stored n=41 over 24 actual `#include` lines) has a **wrong reference on the
pinned engine** — 41 was never the right answer. Rust was already correct, which is why it did not
move.

**`::callees` was returning descendant calls, making it redundant.** On `py-variety`'s
`deep_nesting.py`:

```
pinned   .fn#level2::callees  n=5  == .fn#level2 .call  n=5   <- identical: just descendant calls
latest   .fn#level2::callees  n=1     .fn#level2 .call  n=5
```

The pinned `::callees` was exactly `.fn#X .call`, so it counted calls made inside *nested*
functions as level2's callees. The latest returns the one call in level2's own body. That makes
`::callees` mean "the functions this one calls" rather than duplicating a descendant selector.

**So re-pinning does not cost 6 pairs — it corrects them.** Of the six mismatches, five are these
two fixes (`.import` ×1, `::callees` ×1, and the bash `.call` change ×3 via `:has()`), and the
pinned reference is the incorrect one in each. The only change I still cannot adjudicate from
outside is the bash `.call` broadening (39 → 362, with `.access` 597 → 920, `.fn` and `.member`
untouched): treating every bash command as an invocation is defensible and looks deliberate, but
whether it is intended is the one question worth asking.

**The transferable risk this exposes:** our pinned references can be *wrong*, not merely different,
and an execution-verified corpus cannot detect that by construction — `verify.py` confirms a
selector's node set is stable and that distractors differ, never that the engine's classification
is right. `ho-0060` passed every gate with an answer inflated 1.7x. **Re-verification against a
newer engine is the only check that catches this class of error**, which is an argument for
re-pinning periodically rather than treating the pin as a safety measure.

**Filed:** sitting_duck **#191** (`:calls()`/`:called-by()` discard a selector or empty argument)
and a comment on **#188** documenting the compound-widening form (`.fn.zzzUnknown` == `.fn`).

## The train-card x eval-card 2x2: the card makes the model card-DEPENDENT

Arm D (A's build config plus the 491 vocabulary pairs, cards held at v1) scored 80.2% on the
holdout under `card_pd.md` and 76.8% under `card_v2.md` — the same adapter, the same weights, 3.4
points apart on the inference prompt alone. On that one observation I said the three replications
of the "card tax" were probably an eval-prompt effect and that my memory note had the mechanism
wrong. **Completing the 2x2 shows that was an overcorrection.** Every cell on the old pin:

```
holdout                      eval_vocab                   holdout_rw          eval_t5
train    eval pd  eval v2    eval pd  eval v2             pd      v2          pd      v2
v1        79.3%    78.3%      10.6%    26.5%  (+15.9)    79.1%   79.1%       83.1%   83.1%
v1+p      80.2%    76.8%      84.1%    85.8%  ( +1.8)    72.4%   71.4%       81.4%   80.5%
v2        75.5%    74.0%       8.8%    21.2%  (+12.4)    70.8%   70.8%       83.1%   81.4%
v2+p      73.7%    77.1%      56.6%    85.0%  (+28.3)    67.4%   69.4%       80.5%   80.5%

train-card main effect (v2 cards - v1 cards), averaged over eval cards:
   holdout -3.6    holdout_rw -5.9    eval_vocab -8.8    eval_t5 -0.6
```

**1. The card tax is a TRAINING effect, and my original note was right.** Averaged over both eval
cards and both pair conditions, training on the v2 cards costs **−3.6 holdout** and **−5.9
holdout_rw**. The eval-card deltas, by contrast, have no consistent sign (−0.9, −3.4, −1.5, +3.4;
mean −0.6) and mostly sit inside the 2.5-point noise floor. Arm D's −3.4 was the largest of four
and I generalised from it. The magnitude is −3.6, not the −5.3 I first reported, because that
number confounded the train and eval cards.

**2. The finding worth keeping: the card addendum makes the model depend on the card.** Look at
`eval_vocab` under `card_pd.md`, a card that never mentions `.def`, `::scope` or `::parent`:

```
  v1+p (trained on EXAMPLES only)   84.1%  ->  85.8% with the card     drop without it:  1.8
  v2+p (trained WITH the card)      56.6%  ->  85.0% with the card     drop without it: 28.4
```

Both arms reach ~85% when the card is present. Remove it at inference and the example-taught model
loses **1.8 points** while the card-taught model loses **28.4**. Documenting the vocabulary in the
card taught the model to *read the card* rather than to know the language; teaching the same
vocabulary by example internalised it. That is a mechanism for the tax, not just a cost: card rows
spend capacity on prompt-following.

**3. The pairs work with no card support in either place.** D under `card_pd` reaches **84.1%** on
eval_vocab against arm A's 10.6% on the identical prompt — **+73.5 points** from 491 pairs, with
the original cards at training time and an eval card that documents none of the constructs. The
card alone, with no pairs, buys +15.9 (A: 10.6 -> 26.5) and +12.4 (B': 8.8 -> 21.2). So examples
beat documentation by roughly 5x on the suite the documentation was written for.

**4. Best holdout of the session: D under `card_pd`, 80.2%** — the only arm to exceed arm A (79.3,
and inside the noise floor of it). Net: the vocabulary is free on the existing suite if it is
taught by example and the card is left alone.

**Practical rule, now with a mechanism:** add constructs as pairs, never as card lines; and if a
card must grow, expect the model to become dependent on it. The corollary is a cheap deployment
check — score with the short card and see how far the model falls.

**The paraphrase brittleness is partly the v2 corpus, not the pairs.** holdout_rw's train-card
effect is −5.9, larger than the holdout's −3.6, and D (v1 cards + pairs) still drops 72.4 vs 80.2
original-to-reworded. So the pairs carry some of it too; the instrument question stands open.

## Re-pinned to sitting_duck v1.15.4, and a digest-only re-pin would have been wrong

`v1.15.4` (`803b35b`, tagged 2026-10-03) is the first **release** containing the #184 fix — it is
the merge of PR #185. Built from a detached worktree at the tag into
`workspace/engine/sd-v1.15.4-803b35b`, reproducible, no dependence on anyone's working tree. The
peer's `048bd59` was rejected as a pin target because its tree was dirty; probing both showed every
behaviour change belongs to the release, with `::call-sites` the only WIP-only addition.

**The price was 4x what the digest check said, and in a different shape.** `workspace/refcheck.py`
compares stored `reference.sha256` to a fresh execution and found 6 moved references. That is
necessary and not sufficient: a semantics change can leave a reference untouched while making a
**distractor collide** with it (the pair stops discriminating) or a **modifier vacuous** (the pair
stops testing the modifier). `workspace/repin_verify.py` re-runs the real gates by calling
`verify.verify()` — the same code that accepted these pairs, so the standard cannot drift:

```
eval_vocab  113   ok 113
eval_t5     118   ok 107   FAILS GATES 11   (all 11 oracle-sourced)
holdout     323   ok 320   FAILS GATES  3   + 2 references merely moved
holdout_rw  301   ok 298   FAILS GATES  3   + 2 references merely moved
```

**What a digest-only re-pin would have done:** `ho-0013` (`.call`, "every invocation") moved 39 ->
362 nodes, so it would have been "fixed" by storing 362 — creating a pair that violates the
suite's own 1..50 bounds gate and asks a model to select 362 nodes. `ho-0004`
(`.fn:has(.call)`) would have been stored at 3 nodes while `:has(.call)` is no longer
load-bearing, leaving a pair that tests nothing. Two of the six "moved" pairs needed retirement,
not re-referencing, and the digest check cannot tell those cases apart.

**Actions taken.** Retired 3 holdout pairs and their reworded counterparts — `ho-0004`
(`:has(.call)` vacuous: bash commands now count as calls), `ho-0005` (0 nodes), `ho-0013` (362
nodes) — all three traceable to the one bash `.call` change. Re-referenced `ho-0060` (41 -> 24,
the inflated `.import`) and `ho-0367` (15 -> 16) in both suites, and `t5-p55` (`::callees`
5 -> 1). Retired the **13 oracle-sourced eval_t5 pairs**: 11 fail the gates outright on v1.15.4
(5 use attribute filters inside `:has()`, which the engine now refuses explicitly; 3 use
`:scope(X)`, retired by #184; the rest went vacuous or out of bounds), and the earlier
adjudication had already found zero engine agreement across all 13. eval_t5 is now its 105
engine-verified pairs, which every report already treated as the headline.

```
after the re-pin:  holdout 320   holdout_rw 298   eval_vocab 113   eval_t5 105
confirmation run:  836 of 836 pairs pass every gate, zero failures
```

Every reference in all four suites now carries `source: "engine"`. The three suites that had no
`source` key at all were stamped only after re-executing them (113/113, 320/320, 298/298 clean),
so the stamp is earned rather than assumed.

**Two fixes to the harness, both of which had already cost measurements.**

`verify.py`'s `SD` default was `~/Projects/sitting_duck` — the **live** checkout, whose build and
macros move under us. That default is what silently invalidated three measurements earlier (two
engines compared as one). It now defaults to the pin, with `SITTING_DUCK`/`ASTCSS_MACROS` still
overriding for deliberate cross-engine probes. An unset environment can no longer reach a moving
engine.

`qualify.rescore()` indexed `pairs_by_id[r["id"]]` unconditionally, so any run generated before a
retirement would `KeyError`. It now skips retired answers **and prints them** — a silently
shrinking denominator is precisely how a re-pin would flatter every earlier arm.

Arm D's holdout is 80.2% on the old pin and 80.3% on the new one (257/320), so the re-pin does not
move the comparison; it removes three pairs that no longer mean anything and one reference that was
simply wrong.

## Haiku 4.5 as an instrument: the tuned 0.8B wins, the rewording suite is vindicated, and my bad-pair detector was built on a false premise

All numbers on the v1.15.4 pin, 33 runs rescored onto it.

```
model                         holdout      eval_vocab     holdout_rw
A  0.8B tuned (v1 cards)    79.1% (320)   10.6% (113)    79.2% (298)
B' 0.8B tuned (v2 cards)    73.8%         21.2%          70.8%
C' 0.8B v2 cards + pairs    77.2%         85.0%          69.5%
D  0.8B v1 cards + pairs    80.3%         84.1%          72.5%
Haiku 4.5 (card_v2)         74.7%         76.1%          77.2%
```

**1. A 0.8B fine-tune beats Haiku 4.5 by 5.6 points on the holdout and 8.0 on eval_vocab** — and
eval_vocab is the suite of constructs Haiku had fully documented in its context. That is the
project's thesis, measured: 491 verified pairs and a 3.2-hour QLoRA run buy more on this task than
a frontier model reading a specification. Haiku wins the reworded suite (77.2 vs 72.5), which is
the next section.

**2. `holdout_rw` is a valid instrument, and I was wrong to suspect it.** I had found one reworded
query that changed the question and suspected the suite was partly measuring its own paraphrase
noise. Paired on the 298 common ids, original wording vs reworded:

```
A  (no pairs, v1 card)   +1.3        C' (pairs, v2 card)   -6.4
B' (no pairs, v2 card)   -1.3        D  (pairs, v1 card)   -6.7
Haiku 4.5                +4.0
```

**Haiku gets 4 points BETTER on the reworded queries, and the control gains 1.3.** The reworded
phrasings are not broken — they are if anything clearer (they are longer and more explicit). The
drop is a property of the arms that drop.

**3. The brittleness is caused by the vocabulary pairs, not the card — which corrects what I said
earlier.** I had claimed "23 of C's 37 regressions are shared with B', so the brittleness is mostly
the card and the v2 training". The arm-level paired numbers say the opposite: both no-pairs arms
sit inside the noise floor (+1.3, −1.3) and both pairs arms drop ~6.5 **regardless of which card
they trained on**. Counting shared regressions between two arms that differ in one factor was the
wrong statistic; the factorial comparison is the right one.

**4. The mechanism: my vocabulary pairs taught frames that CONFLICT with the holdout's own
labels.** The holdout contains these pairs, and they are the ones every model misses:

```
ho-0015  "where is AstVisitor defined"        -> .fn#AstVisitor
ho-0019  "jump to the NodeFieldPrinter definition" -> .fn#NodeFieldPrinter
ho-0125  "where is string actually used"      -> .call#string
```

My 491 pairs teach `where is {n} defined` -> `.def#{n}` and `every use of {n}` -> `.name#{n}`.
Those are the *same frames* with *different* answers. Rewording a holdout query makes it longer and
more explicit — which makes it **more** likely to match a vocabulary frame, which is precisely why
the pairs arms lose ground on rewording while the control and Haiku gain it. The vocabulary did not
make the model worse at astcss; it made the model answer a different question than the holdout asked.

**5. My bad-pair detector rested on a false premise, and the probe says so.** The premise was that
"a pair every model misses is likelier a bad pair than several independent capability failures".
14 of 320 holdout pairs are missed by all four models (4.4%), 11 of them `named-fn`. Executing the
alternatives shows **the references are correct**:

```
ho-0015   .fn#AstVisitor  n=1  <= reference      .class#AstVisitor  n=0   <- every model's answer
ho-0018   .fn#JsonVisitor n=1  <= reference      .class#JsonVisitor n=0
ho-0071   .fn#StrQuote    n=2  <= reference      .class#StrQuote    n=0
```

`.class#X` returns **zero nodes**. The models are not finding a defensible alternative reading —
they are wrong, together, because they share a prior: a CamelCase identifier looks like a class, so
they answer `.class#X`, when in C, C++, Go and TypeScript these are functions. **The failures are
not independent, so consensus cannot detect a bad pair.** Correlated priors are exactly what
defeats this design, and a frontier model shares the prior rather than breaking the tie.

The detector's yield of bad pairs was therefore about zero — but it found a crisp, trainable model
weakness instead: **CamelCase name -> `.class` bias**, costing ~3.4 points of holdout on its own
(11 of 320). Pairs where a capitalised name is a function are a concrete corpus gap.

Two genuinely ambiguous pairs did surface: `ho-0125`/`ho-0364` ("where is X actually used") have
reference `.call#X` while every model answers `.name#X`, and the two differ by one node each
(the call expression vs the identifier inside it, adjacent node ids). Those are under-specified
rather than wrong, and the holdout has no distractors to adjudicate them.

### Correction: the frame conflict is ~20% of the brittleness. The rest is the two new constructs failing to discriminate from each other

I wrote that the vocabulary pairs' frames colliding with the holdout's labels was "the mechanism"
for the 6.5-point paraphrase loss. Auditing it says that was too strong.

**Exact frame collisions are 18 of 320 holdout pairs**, all of them `def` frames
("where is {n} defined") whose reference is `.fn#{n}`. On those 18, A gets 14 and D gets 10 — a
loss of 4 pairs, **−1.25 holdout points** — and D's reworded score on them is *better* (13/18),
which a frame-collision story does not predict.

Decomposing D's extra loss relative to A across the 298 paired ids, by whether the request uses
definition or reference language at all:

```
group          n     A orig -> rw          D orig -> rw          D-A      contribution
def-keyword   85   84.7% -> 82.4% (-2.4)  81.2% -> 76.5% (-4.7)  -2.4        -0.67
name-keyword  10   30.0% -> 60.0% (+30.0) 40.0% -> 40.0% ( 0.0) -30.0        -1.01
other        203   77.3% -> 78.8% (+1.5)  80.3% -> 72.4% (-7.9)  -9.4        -6.38
                                                                 TOTAL       -8.05
```

**The loss lives in `other` — the 203 pairs that use no definition or reference language
whatsoever** — contributing −6.4 of the −8.1. The frames that actually collide account for about
−1.7, roughly a fifth. So the conflict is real and I quantified it, but it is not the mechanism.

**What the mechanism is.** Of D's 27 regressions among those 203, the prediction's head class
changes like this:

```
def -> name   5      call -> fn      4      call -> class  3
call -> call  2      call -> call,class 2   fn,try -> catch,fn 2
```

`def -> name` is the tell: the model answered `.def#X` on the original phrasing (**correct** — it
matched the reference) and `.name#X` on the reworded one. Both are constructs the 491 pairs
introduced, and the pairs taught them with semantically adjacent frames — "where is {n} defined"
versus "every use of {n}". **The two new constructs do not discriminate from each other under
paraphrase, and they bleed onto requests that are about neither.** That is why the loss is
diffuse across `other` rather than concentrated where the frames collide.

**This is the defect the corpus was never built to prevent.** `eval_t5` carries 236 distractors
across 118 pairs; `holdout`, `holdout_rw` and `eval_vocab` carry **zero**. The vocabulary pairs
were generated from frames with no contrastive pressure at all — nothing in the 491 ever told the
model that "where is X defined" and "every use of X" must get *different* answers. Adding a
construct by example teaches its form; it does not teach its boundary.

**Next:** discrimination pairs that contrast `.def` / `.name` / `.call` / `.fn` on near-identical
phrasings, with verified distractors, and a retrain. The prediction to record before building it is
that this recovers the `other` group's −6.4 without giving back eval_vocab's +73.5, because the
constructs are already learned — only their boundaries are not.

## The eval_defname baseline refuted arm E before it was trained: D already discriminates, and my contrastive frames make it WORSE

I built 174 contrastive training rows to fix a discrimination failure, then baselined the existing
arms on the 86 held-out contrast pairs before training. The baseline killed the premise.

```
eval_defname (86 pairs, card_pd.md)       A (no vocab pairs)    D (491 vocab pairs)
  overall                                      43.0%                 89.5%
  by construct   def  n=26                     38.5%                100.0%
                 call n=34                     79.4%                 79.4%
                 name n=26                      0.0%                 92.3%
  by phrasing    terse    n=48                 41.7%                100.0%
                 explicit n=38                 44.7%                 76.3%
```

**D already discriminates `.def` / `.name` / `.call` at 89.5%.** The 491 vocabulary pairs taught
the boundary after all. So "the two new constructs do not discriminate from each other" — which I
wrote as the mechanism one section ago — is wrong as stated: they discriminate fine when the
request is terse.

**And the direction is inverted: D scores 100% on terse requests and 76.3% on explicit ones.** All
nine misses are explicitly-framed, and every one is over-elaborated:

```
  "the call sites of Just, not its definition"     .call#Just      -> .call[receiver="Just"]
  "the call sites of fst, not its definition"       .call#fst       -> .fn#fst::callees
  "the call sites of _new, not its definition"      .call#_new      -> .fn#_new::callees
  "every place the name factorial appears, ..."     .name#factorial -> .name#factorial .fn:is-called
```

Adding "not its definition" to a request makes the model reach for *more machinery*, not less. A
verbose request correlates with a complex answer in the training distribution, so the contrastive
clause reads as a demand for extra constructs. **My contrastive frames are the defect they were
meant to cure**, and training 834 rows of them would have taught the coupling harder.

**Partial support on the holdout, stated as partial.** The reworded suite's requests are longer
(4.4 -> 5.2 words), and D drifts toward multi-piece answers five times more than the control:

```
one-piece-answer rate   A  78.5% -> 77.5%  (-1.0)      D  79.9% -> 74.8%  (-5.0)
D's 35 reworded regressions: 13 more complex, 14 same, 8 simpler; mean 1.37 -> 1.54
reference complexity: 1.31 pieces
```

So verbosity-to-complexity coupling is real and stronger in D, but it accounts for roughly a third
of the regressions, not all of them. I have already over-claimed one mechanism in this thread and
am not going to do it again: the remainder is unexplained.

**Arm E is cancelled.** Training 834 rows of explicit contrastive framing would train the exact
coupling that produces the failure. The baseline cost ~4 minutes of generation and saved a 3.5-hour
run that the evidence says would have regressed the holdout.

**Why this nearly went wrong, which is the transferable part.** `eval_defname` is
**survivor-shaped**: the generator only offered names present in both `fn_names` and `call_names`,
so 69 names were eligible and **136 defined-but-never-called names were never offered to the gate
at all**. Every pair in the suite is a case where discriminating is correct, so a high score there
is compatible with a model that over-discriminates — the suite can measure acquisition and
structurally cannot measure over-firing. The holdout is the control for that, and it is where the
cost showed up. The gate's 284/300 and 260/276 yields with **zero** distractor collisions should
have been the tell: a gate that rejects nothing is not filtering, it is confirming that the
population was pre-filtered.
