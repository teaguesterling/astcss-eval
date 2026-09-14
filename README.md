# astcss-eval

An execution-verified evaluation set for translating plain-English code-search
requests into astcss selectors (the CSS-style selector language of
[sitting_duck](https://github.com/teaguesterling/sitting_duck)'s `ast_select`),
and the harness that scores local and cloud models on it.

- `SPEC.md` — the design this set implements (tiers, scoring, generator rules)
- `SCHEMA.md` — the pair format, acceptance gates, pending and retired pairs
- `FINDINGS.md` — engine defects, taxonomy gaps and pair defects found along the way
- `fixtures/` — pinned source trees with a manifest (`py-variety`, `repo-small-py`)
- `candidates/` → `pilot.py` → `pairs/` — candidate batches, verified and frozen
- `verify.py` — execution verifier (bounds, load-bearing modifiers, distractors)
- `card.md`, `card_v2.md` — vocabulary cards used as the system prompt
- `qualify.py` — model qualifier: Tiiny device models (NPU-yielding, one at a
  time) and Anthropic models via `claude -p`, scored by execution match
- `runs/` — qualifier results (stage 1: 12 models × 40 pairs; stage 2: 4 models ×
  109 pairs × two cards)

Running the verifier needs a sitting_duck build (`SITTING_DUCK`, default
`~/Projects/sitting_duck`) and the selector macros named in `verify.py`.

Extracted from the Tiiny workspace (`eval/astcss` on branch
`eval/astcss-validation`) with its history.
