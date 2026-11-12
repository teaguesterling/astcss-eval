# A mutator tier: jQuery-style mutations on the execution-verified frame

*Proposal, 2026-09-16. Not results — FINDINGS.md is for those. This says what a mutator tier would
have to be, what already exists, and what the cheapest experiment is that could kill it.*

The idea: today a pair is `request -> selector`, verified by executing the selector and comparing the
node set. A mutator pair would be `request -> selector + operation + argument`, verified by applying
the mutation and comparing the result. jQuery's shape — select, then act on the selection.

The headline for planning: **this is a new tier on the existing frame, not a new project**, and it is
much further along than "we haven't formalized that API yet" suggests. pluckit already implements 14
mutation operations with a documented chain grammar and a sound safety gate, and sitting_duck's
`feat/ast-patch` branch already has a pure, byte-exact patch primitive. Neither existed as far as this
eval was concerned a day ago. What is *not* in place is the verification story, and that is the part
this note is mostly about.

---

## 1. The vocabulary that already exists

`pluckit.chain.Chain.MUTATION_OPS` — public and SemVer-stable, which is what squackit's safety gate
reads — contains 14 operations. Arities from `pluckit/src/pluckit/selection.py`:

| Op | Arity | Argument kind | Lowers to (ast_patch kind) |
|---|---|---|---|
| `remove` | 0 | — | `delete` |
| `unwrap` | 0 | — | `replace` (drop first/last line, dedent) |
| `rename` | 1 | identifier | `replace` (name occurrence) |
| `addParam` | 1 | param text | `replace` (signature) |
| `removeParam` | 1 | param name | `replace` (signature) |
| `addArg` | 1 | expression | `replace` (call args) |
| `removeArg` | 1 | kwarg name | `replace` (call args) |
| `prepend` | 1 | code block | `insert_before` (first body child) |
| `append` | 1 | code block | `insert_after` (last body child) |
| `patch` | 1 | unified diff *or* raw text | `replace` |
| `replaceWith` | 1 or 2 | code, or `old -> new` | `replace` |
| `wrap` | 2 | before, after | `insert_before` + `insert_after` |
| `insertBefore` | 2 | **selector**, code | `insert_before` (anchor descendant) |
| `insertAfter` | 2 | **selector**, code | `insert_after` (anchor descendant) |

Two things to notice, because they shape everything downstream.

**All 14 lower onto four edit kinds.** `ast_patch` accepts exactly `replace`, `delete`,
`insert_before`, `insert_after`. The surface vocabulary is 14 verbs; the verification substrate is 4
primitives. That is a good ratio — it means the oracle does not need 14 implementations.

**Two ops take a selector as an argument.** `insertBefore`/`insertAfter` resolve their first argument
as a CSS selector against each matched node's subtree (first descendant wins). So the answer for those
is not two-part but *three*-part, and one of the parts is itself an astcss selector — the thing we are
already training. These are the most interesting pairs in the tier and should not be deferred to last.

### Dead tokens

`_KNOWN_OPS` also contains `clearBody` and `replace`, which are in **no** category set
(`_TERMINAL_OPS`/`_QUERY_OPS`/`_NAV_OPS`/`_MUTATION_OPS`/`_PLUGIN_OPS`). `mutations.py` has a
`ClearBody` class that was never wired to a `Selection` method. Verified by parsing (never evaluating):
a chain containing either raises `ValueError: Unknown chain op`. They are not a safety-gate bypass —
there is no method to dispatch to — but they are live tokens in the grammar, which matters below.

---

## 2. The constraint that decides how pairs can be written

`Chain.from_argv` uses `_KNOWN_OPS` membership to decide **token boundaries**: a token that spells an
op name starts a new step instead of becoming an argument to the current one. argv is whitespace-split,
and shlex quoting at the squackit layer does not rescue it, because the collision is decided after
splitting. Verified by parse-only test:

```
find .fn#old rename new_name   ->  [('find', ['.fn#old']), ('rename', ['new_name'])]      OK
find .fn#old rename replace    ->  [('find', ['.fn#old']), ('rename', []), ('replace', [])]
find .fn#old rename text       ->  [('find', ['.fn#old']), ('rename', []), ('text', [])]
```

`rename replace` produces a `rename` step with **zero arguments**, which then fails at evaluate time
with a `TypeError` about a missing positional argument — an error that never names the actual problem.

So: **a mutator pair whose argument contains a token spelling any of the ~40 `_KNOWN_OPS` names is
unrepresentable in the chain grammar.** `rename text`, `rename count`, `rename patch`, `append remove`
are all unwritable. This is a generation-time gate, not a caveat to document — the generator must
reject such pairs, or the corpus teaches a model to emit chains that cannot parse.

It is worth noting these names are ordinary English words a model *will* reach for. This is the single
most likely source of silent corpus corruption in the tier.

---

## 3. Two oracles that will disagree — and that is the design

This is the part worth getting right, and it maps exactly onto the oracle-first architecture already
validated for selectors (581 pairs in, 581 out, zero reference changes).

There are two independent implementations of "apply this mutation":

**`ast_patch` (sitting_duck `feat/ast-patch`, commit 100b9e1)** — pure. Takes edit rows anchored at AST
byte positions, re-reads the files, returns `(file_path, patched_source)`. Writes nothing. Byte-exact:
`start_column`/`end_column` are 1-indexed byte offsets, end exclusive, sliced as BLOB ranges so
multi-byte characters cannot shift an anchor. Validates loudly and never emits partial output: unknown
edit kind, NULL positions, uncovered file, position out of range (a staleness guard), and overlapping
edits all raise.

**`pluckit.MutationEngine`** — line-granular and in-place. Snapshots each affected file, splices
`[start_line, end_line]`, writes with `Path.write_text`, re-parses to validate syntax, rolls back all
files on any error.

The engine's own docstring states why it is line-granular:

> "Because sitting_duck's `read_ast` doesn't expose byte offsets or column positions, the engine
> operates at line granularity."

**On `feat/ast-patch` that premise is no longer true.** This is the most consequential thing found
while writing this note, and it is actionable for pluckit independently of whether this tier ever
gets built (see §7).

Concretely, the two will disagree. `Rename.compute` is `old_text.replace(name, self.new_name, 1)` over
the node's **entire line range** — first occurrence wins. Prediction, to be tested rather than
asserted: where a node's range includes text before the definition name — a Python decorated
definition, an attribute or annotation, a doc comment — the first occurrence is not the definition
name, and pluckit renames the wrong token while `ast_patch` anchored at the name node renames the right
one. Whether tree-sitter's node boundaries actually put a decorator inside the matched range is a
question for a fixture, not for reasoning.

**So run it the way selectors already run.** The oracle computes the documented semantics; the engine
confirms; a disagreement is a filed finding, not a rejected pair. Three outcomes, unchanged:
`verified` / `pending_engine:<issue>` / `rejected`. The tier gets the same defect-triage machinery that
recovered 230 pairs after #145 and #151.

### What the reference should be

Not the byte-exact patched text, even though it is available and tempting because it is exact.

Presentation is the problem: pluckit's mutations explicitly "inherit the indentation" of their target,
and `prepend`/`append` compute insertion points by scanning for body boundaries. A semantically correct
chain that differs by one space would score wrong, and the tier would measure whitespace agreement
rather than comprehension.

**Reference = re-parse the patched source and compare node tables** (structural equality), with the
byte-exact `patched_source` retained as the audit artifact next to it. Syntactic validity is already
guaranteed on the pluckit path by its re-parse step. This keeps the tier measuring the same thing the
selector tiers measure — engine-observable structure — and keeps the exact text for human review in
the pair browser.

---

## 4. How the six gates map

| Gate | Carries over? |
|---|---|
| Bounds (1–50 nodes) | Unchanged — it bounds the *selection*, which still exists |
| Load-bearing modifiers | Unchanged — drop a modifier, the selection must change |
| Distinct distractors | Unchanged, but distractors now differ in selector **or** op **or** argument |
| No duplicate node set | Becomes **no duplicate (node set, patch)** — same selection, different mutation is a legitimately distinct pair |
| No eval overlap | Unchanged |
| Request determines the selector | Becomes request determines selector **and** op **and** argument — strictly harder to satisfy, and the audit gate that retired pairs before will retire more here |

Two new gates the selector tiers had no need for:

- **Applicability.** `addParam` on a node that is not a function, `removeArg` on a call with no such
  kwarg, `unwrap` on a single-line node — these are not wrong answers, they are inapplicable requests.
  The generator must confirm the op is meaningful for every node in the selection.
- **Non-overlap.** `ast_patch` errors when edits overlap, and a selector matching both a node and one of
  its descendants is the documented usual cause. `wrap` over nested matches (a `.fn` inside a `.fn`, a
  `.call` inside a `.call`) will hit this constantly. Non-overlap has to be checked at generation time,
  not discovered at scoring time.

---

## 5. Constraints this imposes on the harness

Three things that are not obvious and would each cost a day if found late.

**In-place mutation voids the result cache.** `verify.py:_fixture_key()` hashes every glob-expanded
fixture file by path, size and `st.st_mtime_ns`. `MutationEngine` writes files and restores content on
rollback — but not mtime. So every mutator verification through pluckit silently invalidates the cache
that took batch verification from 16m41s to 4m57s. Strong argument for making **`ast_patch` the primary
path** (pure — nothing is written, cache stays valid) and pluckit the confirmation path, run against
per-shard fixture copies.

**Mutations cannot shard over shared fixtures.** `_execute_sharded()` runs shards concurrently against
the same fixture tree. `MutationEngine` writes real files, and its rollback is explicitly
`pass  # best-effort rollback`. Concurrent shards mutating one tree is corruption, and a best-effort
rollback means the corruption can be silent. Per-shard fixture copies, or a pure oracle — not both
optional.

**The argument part is partly transcription.** Nothing but the request can determine *what* to rename
something to, so the argument must appear near-verbatim in the request. A model that copies a string
scores as if it understood the mutation. **Score selector-part, op-part and argument-part separately**,
or the tier's numbers are not comparable to the selector tiers' and will look inflated.

---

## 6. Proposed tier structure

Ordered by how much the answer adds beyond a selector the model can already produce:

- **M1 — zero-argument ops** (`remove`, `unwrap`). Answer is selector + op. No transcription, so this is
  the cleanest measurement of whether the op itself is understood.
- **M2 — one literal argument** (`rename`, `addParam`, `removeParam`, `addArg`, `removeArg`).
- **M3 — body insertion** (`prepend`, `append`). Indentation-sensitive; the first tier where the
  structural-comparison decision in §3 earns its keep.
- **M4 — two-argument structural** (`wrap`, 2-arg `replaceWith`). First tier that produces two edits
  from one op, and the first to meet the non-overlap gate in anger.
- **M5 — selector arguments** (`insertBefore`, `insertAfter`). Three-part answer containing a nested
  astcss selector. Directly reuses everything the selector tiers taught.
- **M6 — multi-step chains** (navigation between mutations, e.g. `addParam` on a definition then
  `.callers().find('.call#name').addArg(...)` to propagate). This is where the jQuery analogy pays off
  and where a small model will most likely fall over.

My expectation — a hypothesis, not a finding — is that 0.8B will not hold a three-part answer together
and this tier needs 4B+. That is exactly the kind of guess that has been wrong twice in this project
already (few-shot fixing dotted-type errors; the "39/40 agree" sampling artifact), so it should be
measured before any corpus is built.

---

## 7. The cheapest experiment that could kill this

> **Superseded 2026-09-16.** This experiment was run, in a different form: see "Which output
> surface can a small model write?" in FINDINGS.md. Two results change this note. (a) The
> reference/oracle framing in section 3 assumed pluckit would be the counterpart oracle; Teague has
> since said the CSS design is "just a scribble", and pluckit is a MODEL here, not an oracle.
> (b) op+args turns out to be 85-100% for every surface and model while only the selector column
> collapses, so the tier's hard half is selector accuracy -- which a tuned 0.8B specialist already
> supplies at 18/20 on targeting phrasing. A mutator tier should probably be built as a two-model
> pipeline from the start, not as one model emitting a whole mutation.


**Hand-build 20–30 mutator pairs and run them through the existing stage-9 harness** (7 device models ×
plain/card/few-shot). No corpus, no generator, no new verification code — score by hand if necessary.

It answers the only question that matters before investment: can these models emit a well-formed chain
*at all*? Stage 9 showed a 0.0% floor for all seven models without a card and 92.6% for the best with
few-shot, so the harness is calibrated and the comparison is meaningful immediately.

If the answer is "not below 4B", the tier is a 9B project and should be sequenced after the current
0.8B work rather than beside it. If even 0.8B can emit M1 chains, the tier is worth building out
properly.

## What would need to land first

- `feat/ast-patch` merged, or pinned as a second verification-only engine the way `sd-20260915-2001`
  already is.
- A decision on pluckit's line-granular splicing (§3, and "Filed elsewhere" at the end), because the
  oracle's counterpart should ideally be byte-exact too.
- The op-name collision gate (§2) implemented in the generator before any pair is written.

## Filed elsewhere

The three pluckit findings — the stale line-granularity premise, the two dead tokens, and the
argument-stealing token boundary — belong to a different repo than this eval and than the sitting_duck
issues. Routed via `~/.claude/inbox/pluckit-chain-grammar.md` rather than opened as issues, pending a
decision on whether they are worth filing.
