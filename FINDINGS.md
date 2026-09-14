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
