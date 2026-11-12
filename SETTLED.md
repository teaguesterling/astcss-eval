# Settled state — 2026-10-09

The configuration everything after this date is measured against. Pinned deliberately: five
explanations for the rewording gap have been falsified, so further work is inference-time or
data-augmentation experiments **against this baseline**, not a moving target.

## The configuration

```
engine        sitting_duck v1.15.4 (803b35b), workspace/engine/sd-v1.15.4-803b35b
              verify.py defaults to it; SITTING_DUCK/ASTCSS_MACROS override for cross-engine probes
base model    Qwen/Qwen3.5-0.8B
adapter       workspace/adapters/t5-v1full/epoch1          ("arm D")
eval card     card_pd.md                                   (NOT card_v2.md -- see note)
```

Reproduce the adapter:

```
python3 tune/build_dataset.py t5-v1full --system per-language --card card_v1c.md \
    --cap-template 8 --val-frac 0.1 --seed astcss-train-v1 --cards-dir train/cards \
    --extra-pairs workspace/trainset-t5/pairs.jsonl \
    --extra-pairs train/candidates/vocab-train.jsonl          # 16,288 train rows
python3 tune/train_qlora.py --base <qwen3.5-0.8b> --quant none --data workspace/datasets/t5-v1full \
    --out workspace/adapters/t5-v1full --epochs 1 --accum 16 --lr 2e-4 --seed 18 --max-len 1024
```

## The numbers

```
suite                 n     arm D     control A   Haiku 4.5    notes
holdout             320     80.3%        79.1%      74.7%       best of the session
holdout_rw          298     72.5%       79.2%      77.2%       the known gap
eval_vocab          113     84.1%       10.6%      76.1%       +73.5 from 491 pairs
eval_t5 (engine)    105     81.4%       84.8%        --        RW arm is best here at 91.4%
```

Noise floors: holdout **2.5** points (seeds 18/19/20/21), eval_t5 **8.3** points.

## Why these choices

- **`card_pd.md`, not `card_v2.md`.** The 2x2 showed training on the v2 cards costs 3.6 holdout
  points and makes the model *depend* on the card: remove the card at inference and an
  example-taught model loses 1.8 points while a card-taught one loses 28.4. The vocabulary is
  taught by the 491 pairs; the card addendum is not needed and is not free.
- **Arm D, not C'.** Same pairs, original cards. D is the only arm to exceed the control's holdout.
- **eval_t5 is the 105 engine pairs.** The 13 oracle-sourced pairs are retired: 11 fail the
  verification gates on v1.15.4 and an adjudication found zero engine agreement across all 13.

## Known limitation, characterised and unexplained

Paired on 298 ids, original phrasing vs model-reworded: control **+1.3**, Haiku **+4.0**,
arm D **−6.7**. Every intervention that changed the training *request* distribution cost ~6 points
of this, whether it added pairs or only swapped paraphrase authorship at constant rows; changing
card text alone did not. Five explanations falsified (length/register, synonym rarity, synonym
presence, phrasing diversity in training, frame collision) plus one refuted outright (construct
non-discrimination). The style-matching account predicts the opposite of the observed result.

**On in-distribution phrasing the tuned 0.8B beats Haiku 4.5 by 5.6 points; on reworded phrasing
Haiku beats it by 4.7.** That is the shape of what remains.

`holdout_rw` carries a single `reword_model` hash, so "robust to rewording" currently means robust
to one model's voice. Mixing reword models is untested and would be the first thing to check before
trusting the gap's size.
