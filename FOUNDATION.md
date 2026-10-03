# Rebuilding the foundation — what this session measured that a v2 should assume

Written 2026-10-03, after a session in which four training interventions each lost holdout
accuracy and the untouched control beat models 11x its size. Every item below is a measured
finding with the number attached, not a preference. If the foundation is rebuilt, these are
the decisions that should come out differently, in roughly the order they bite.

## 1. Build the generalisation instrument FIRST, not last

The holdout suite (323 pairs, 11 languages, repos in no training fixture) was built late, and
the moment it existed it INVERTED the ladder:

    model            eval_t5   holdout
    9b-t5-e2          93.2%     73.3%
    4b-t5-e2          90.8%     76.9%
    0.8b-t5-e1        82.4%     79.5%

eval_t5's best model is the holdout's second-worst. Every training decision before that point
was optimising a metric that ranks models in an order generalisation reverses. The cleanest
case has no confound at all -- same model, corpus and seed, epoch count only: epoch 2 gains
+3.2 on eval_t5 and loses 5.2 on the holdout.

**v2: no training run before a held-out suite on unseen repos exists.**

## 2. The eval's requests must not share an author with the corpus

Rewording eval_t5 costs ~20 points; rewording the holdout costs 0.2.

    model         eval_t5 -> reworded    holdout -> reworded
    0.8b-t5-e1     82.4%     61.9%        79.3%     79.1%
    9b-t5-e2       93.2%     73.5%        69.7%     65.8%

eval_t5's requests were authored by the process that wrote the training pairs, so a fifth of
its score is familiarity with phrasing. The holdout's were written fresh, and there is nothing
left for a rewording to take.

**v2: eval requests authored independently, and every suite ships a reworded twin from day
one.** The twin is cheap (a model reword plus an identifier guard) and it is the only check
that separates selector skill from phrase recall.

## 3. Register is a PROMPT axis, not a model axis — balance it deliberately

Measured on 120 queries: Haiku, Sonnet and the Tiiny's Qwen3-30B differ from each other in
capitalisation (3/36/0%), imperative share (18/41/10%) and terseness (27/15/5%) -- and ALL
THREE produce 0% interrogatives, exactly like the 4B whose register collapse cost 12 points on
the reworded holdout. The interrogative register is 45% of the human paraphrases and appears in
no model's output.

One generator, asked explicitly, gives 100% questions, 100% terse (<=4 words), 100% verbose
(>=12 words) on demand.

**v2: specify the register mix as a target (question / terse / verbose / imperative /
conversational at stated proportions) and generate against it. Keep the register table as a
pre-flight gate so a batch cannot silently collapse a register.**

## 4. One vocabulary across engine, card and corpus

Today all three disagree:

    card_t5.md:60   teaches `:scope(X)`     -> pinned engine: VACUOUS (84 nodes = all `.fn`)
    the corpus      teaches `:in-scope(X)`  -> pinned engine: unknown pseudo-class, ERRORS
                                               (198 rows)

A model that learns the corpus writes a selector the instrument refuses; one that follows the
card writes a selector that silently matches everything.

**v2: pin the engine, then derive the card AND the corpus vocabulary from that pin
mechanically. A form no longer supported should fail the build, not the measurement.**

## 5. Every reference engine-sourced; no second instrument

13 of 118 eval_t5 pairs carried `reference.source == "oracle"` and were scored against a Python
model of the semantics instead of the engine. Adjudicated: ZERO of the 13 agreed with the
engine -- 8 disagreed, 5 the engine refuses outright. `executes: True` means "the oracle parsed
it" on those and "the engine ran it" on the other 105, with nothing in the row saying which.

**v2: one instrument. A selector the engine cannot execute is not an eval pair.**

## 6. Declination belongs in the corpus from the start

0 of 536 eval pairs were unanswerable; every card said "reply with the selector only"; 33 of
23,796 predictions contained any refusal language. So the model invented on 33 of 33
unanswerable requests -- a protocol gap, not a model defect, and a card granting licence
changed it by exactly zero.

553 declination rows (3.4% of the corpus) took it from 0/33 to 26/33, with ZERO over-refusals
on 16 answerable controls, and 15/33 survived scoring under a card that never mentions
declining -- so the capability lands in the weights.

**v2: declinations are a first-class row type, ~3-5% of the corpus, with answerable controls
and held-out categories to separate transfer from keyword-matching.** (Transfer is partial:
`history` never trained and transferred 4/4; `dataflow` never trained and transferred 0/4.)

## 7. Measure the noise floor before reading any delta

eval_t5's seed range is 8.3 points. Four arms' holdout deltas (-4.6, -9.0, -13.5) were read as
results before the HOLDOUT's seed range had ever been measured. That measurement is cheap --
score existing same-config seed adapters -- and it should gate every claim.

**v2: a suite is not usable until its seed range is known, and no delta smaller than that range
is reported as an effect.**

## 8. Verify the language's limits against the engine, never from intuition

Building the abstention suite I planned a position/ordering category on the assumption that
astcss had no ordering. `.mod > .fn:first-child` returns 3 nodes -- ordering IS expressible,
and the category would have punished correct answers. Separately I claimed the child combinator
was broken because 53 questions were rejected; `>` works fine (`.class#Animal > block` = 2,
`block > .fn` = 46) and my questions encoded the wrong selector for "methods directly on N".

**v2: every expressibility claim carries the probe that establishes it.**

## 9. Declare distractors at authoring time

24 of 98 pseudo-form eval pairs could not withhold credit from a syntactically simpler answer:
8 `:called-by(X)` answered `.fn#X .call`, 4 `::callees` the same, 5 `:calls(X)` answered
`:has(.call#X)`. The gate that catches this already exists (`verify.py` rejects a pair whose
distractor returns the reference's node set) -- those pairs simply never declared one.

**v2: a pair without a declared near-miss distractor is not accepted.**

## What to keep

The engine-execution scoring, the pinned-engine discipline, `verify.py`'s bounds and
load-bearing-modifier gates, `pilot.eval_overlap` as a build-aborting guard (it caught four
real leaks this session, including one I introduced), and the run-output convention that makes
every FINDINGS number recheckable.
