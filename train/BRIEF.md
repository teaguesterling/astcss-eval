# Drafting brief: training pairs for one language

You are drafting **training** pairs for an astcss (CSS-style AST selector) model.
Each pair is a plain-English code-search request plus the one selector that
answers it on a pinned fixture. The verifier decides what is kept; your job is to
propose candidates that are *true of the fixture* and *load-bearing*, then fix
what the verifier rejects.

Everything you need for your language is appended below this brief: the
vocabulary card the model will be prompted with, the fixtures you may use, their
inventories (function, class and call names, common node types), and any
semantic classes the audit found unreliable for this language.

## What you write

One JSON object per line in `train/candidates/<your-batch>.jsonl`:

```json
{"id": "tr-rust-t2-0007", "tier": 2, "fixture": "rs-magic",
 "nl": "calls to unwrap",
 "paraphrases": ["where does the code unwrap a result?", "unwrap invocations"],
 "css": ".call#unwrap",
 "distractors": [".call#expect", ".fn#unwrap"],
 "treeql": null}
```

- `id`: `tr-<language>-t<tier>-<nnnn>`, unique within your batch; never reuse one.
- `fixture`: one of the fixture names listed for your language.
- `nl`: what a developer would actually type. **No selector syntax**: no `#`,
  `[`, `]`, `(`, `)`, `>`, `~`, `+`, `:` and no `.word`.
- `paraphrases`: at least 2, in different registers (terse, question,
  imperative). No two of `nl` + paraphrases may share more than half their
  content words.
- `css`: the canonical selector, written in the vocabulary of the card.
- `distractors`: at least 2 near-miss selectors that parse and run but select a
  *different* node set (a sibling class, a neighbouring name, the other
  combinator, the negated `:has`).

## Tiers

| tier | shape | examples |
|---|---|---|
| T1 | one semantic class or one node type | `.fn`, `.import`, `while_statement` |
| T2 | one class/type plus one filter: `#name`, `[name^=]`, `[name$=]`, `[name*=]` | `.call#unwrap`, `.fn[name^="parse_"]` |
| T3 | exactly two steps joined by ` `, `>`, `~` or `+`; `#name` allowed on either step | `.impl .fn`, `.class#Config .call` |
| T4 | `:has(S)` or `:not(:has(S))` on a class/type, `S` a type, class or `class#name` | `.fn:has(.call#unwrap)`, `.fn:not(:has(.jump))` |

Aim for a balanced batch: roughly equal counts per tier.

## Rules the engine enforces (a candidate breaking them is refused or silently wrong)

- Combinators take **exactly two steps**. `A B C` is refused.
- `[attr]` and `:has`/`:not` filters go on the **last** step only.
- Inside `:has(...)`, only a type, a class and `#name`. No `[attr]` there.
- `#name` is the bare name (`.call#dumps`, never `.call#json.dumps`).
- A node type is written **without** a dot. A dotted unknown name matches nothing.
- Don't use captures (`@x`), `:docblock`, or other pseudo-classes.
- Don't use a class the language notes below mark as unreliable.

## Rules the verifier enforces (read `train/pairs/rejected-<batch>.jsonl`)

- **Bounds:** the selector returns 1-50 nodes on its fixture.
- **Load-bearing:** removing any single filter or combinator step must change the
  node set. If every `open` call is already inside a `with`, `with_statement .call#open`
  is rejected: say "calls to open" instead, or pick a name where the step matters.
- **Distractors:** each must parse, run, and return a different node set.
- **No duplicates:** no two pairs on the same fixture may select the same nodes.
- **NL:** static checks for selector syntax and paraphrase overlap.

## The loop

1. Write a batch of candidates for your language (~40 per tier to start).
2. Verify it (use the absolute interpreter path exactly as written):

   ```
   cd /home/teague/Projects/astcss-eval/trees/train/multilang
   /home/teague/.local/share/venv/bin/python pilot.py train/candidates/<batch>.jsonl <batch> train
   ```

   It prints ACCEPT/reject per candidate with reasons and writes
   `train/pairs/{accepted,rejected,pending}-<batch>.jsonl`.
3. For each rejection, either fix it in a **new** batch file (new ids, e.g.
   `<batch>-r1`) or drop it. Don't edit a batch that has been verified.
4. Stop when your language has the accepted count you were asked for, or when
   further candidates keep failing; report the counts per tier and anything the
   engine seemed to get wrong (a class matching the wrong nodes, a refusal you
   didn't expect). Those reports are valuable, like `FINDINGS.md`.

## Don't

- Don't modify `verify.py`, `pilot.py`, `qualify.py`, any card, `fixtures/`,
  `train/fixtures/`, or anything under `pairs/` (the held-out eval).
- Don't read the eval pairs in `pairs/` or `candidates/` for ideas; training and
  eval must stay independent.
- Don't commit; report what you produced.
- Don't run more than one verifier process at a time.
