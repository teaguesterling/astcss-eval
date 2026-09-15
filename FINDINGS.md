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
