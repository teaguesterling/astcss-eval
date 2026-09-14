# Pair schema

One JSON object per line in `pairs/*.jsonl`. This merges duckent's planned
selector-corpus row — `(treeql, css, fixture, tags)`, see duckent's core design
§7 — with the pair fields in `SPEC.md` §1, so duckent can ingest these rows as
its M2 differential corpus without a translation step.

| field | type | required | meaning |
|---|---|---|---|
| `id` | string | always | `t{tier}-{nnn}`, stable forever |
| `tier` | int | always | SPEC §2 difficulty tier |
| `nl` | string | always | what a developer would actually type; never mentions selector syntax |
| `paraphrases` | string[] | always, ≥ 2 | different registers (terse, verbose, imperative, question); no two share more than half their content words |
| `css` | string | always | the canonical astcss selector — duckent's `css` column |
| `treeql` | string \| null | T3 and above | the TREEQL twin; `null` until duckent can execute TREEQL (M1½) |
| `spellings` | object | optional | engine-specific spellings where an engine needs a different form, e.g. `{"sitting_duck": "…"}`; absent means `css` runs as written |
| `fixture` | string | always | a key in `fixtures/MANIFEST.json` |
| `tags` | string[] | always | duckent's `portable`, `sitting_duck_supported`, `v0`, plus `pending_engine:<reason>` |
| `reference` | object | when `sitting_duck_supported` | the frozen answer: `{"count", "sha256", "nodes"}`, `nodes` being sorted `file:node_id` keys and `sha256` the digest of their comma-join |
| `distractors` | string[] | always, ≥ 2 | near-miss selectors that parse, execute, and return a *different* node set |
| `refusals` | string[] | optional | constructs that must be refused rather than answered (SPEC §1) |
| `captures` | string[] | T9 | expected capture aliases |
| `verification` | object | when verified | `{"batch": <id>, "relaxations": [...], "distractors": [...]}` as returned by `verify.py` |

## Acceptance

A pair is `sitting_duck_supported` only when `verify.py` reports `ok`:

- **executes** — the reference selector runs without error;
- **bounds** — it returns 1–50 nodes: never 0, never the universe;
- **load-bearing** — removing any single modifier (`#id`, `[attr]`, `:pseudo`,
  a combinator step) changes the node set. A modifier that doesn't is
  vacuous, and a model that omitted it would still execution-match;
- **distractors** — every distractor parses, executes, and returns a
  different node set.

Execution alone is not verification: `ast_select` silently ignores unknown and
malformed parts of a selector (sitting_duck issues #127, #128, #130).

## Pending rows

A pair whose selector the current engine cannot honor is kept, tagged
`pending_engine:<reason>`, and **never scored** until an engine executes it.
Reasons in use: `docblock`, `captures`, `where-refusal`, `chain-3plus`,
`attr-in-has`, `file-path`, `in-glob`, `callee-of`, `markdown-vocab`,
`http-vocab`, `jq-dialect`, `umwelt-dialect`.

A pair can also pass every gate while the engine's answer is known wrong. It is
held the same way — `pilot.py` writes it to `pairs/pending-<batch>.jsonl` with
its reference frozen — so the day the engine is fixed, the diff is visible:

- `operator-tokens` — Python `.arith`/`.cmp`/`.logic` include decorator `@`,
  for-loop `in`, and both the expression and its operator token
  (sitting_duck #131)
- `bool-includes-none` — `.bool` is `LITERAL_ATOMIC`, which includes `None`;
  documented as "Boolean literals" (sitting_duck #132)
- `has-syntax-tokens` — inside `:has`/`:not(:has)` an alias also matches
  syntax-only keyword tokens (`def`, `class`, `for`, `as`), which it excludes
  everywhere else (sitting_duck #133)

Node sets are unique per fixture across all batches: a candidate whose node
set or id is already frozen in an earlier batch's accepted or pending file is
rejected, whatever its selector.

## Batches

Every verification run writes `batches/<id>.json` containing
`verify.engine_identity()` — CLI path, extension, sitting_duck checkout, macro
file and its sha256 — so each frozen reference names exactly what produced it.
