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
  * `read_ast` does NOT support `git://` URIs in this build -- the string does not appear in the
    source or the built extension -- so `structural_diff`, which documents that requirement
    (sitting_duck#48), cannot run against our engine. The git:// path is not needed: git_read ->
    parse_ast closes the same loop.
  * duck_tails provides the git table functions (`git_tree`, `git_read`, `git_uri`, `read_git_diff`,
    `git_log`); fledgling's `repo.sql` only wraps them. `file_changes` is a blob-hash join between
    two `git_tree` scans, so enumerating changed files across many commits is a query, not a
    subprocess per file.
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
