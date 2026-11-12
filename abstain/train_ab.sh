#!/bin/bash
# Train declination: baseline corpus + 630 declination pairs, licensed cards.
#
# CONFOUND, stated: the arm differs from the control (0.8b-t5-e1) in TWO ways -- the
# declination rows and the licensed card. Retraining a card-only control is another 3.1 h, so
# instead the arm is scored under BOTH cards. If it declines with the UNLICENSED card too, the
# capability is in the weights, not the prompt -- and we already know the card alone does
# nothing at inference (0 declinations of 33 in all four conditions).
#
# Measured on four things, because the risk is not failure but collateral damage:
#   abstain   the 2x2, split into TRAINED and HELD-OUT categories
#   holdout   accuracy on unseen repos -- must not collapse
#   eval_t5   the headline, for continuity with the rest of FINDINGS
set -u
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
cd /srv/logical/workspace/home/teague/Projects/astcss-eval/trees/tune/setup
L=$PWD/workspace/logs/abstain-train; mkdir -p "$L"; PY=~/.venvs/astcss-tune/bin/python
B08=/home/teague/.cache/huggingface/hub/models--Qwen--Qwen3.5-0.8B/snapshots/2fc06364715b967f1860aea9cf38778875588b17
ENG=/srv/logical/workspace/home/teague/Projects/astcss-eval/workspace/engine/sd-20260914-1835
note(){ echo "$(date +%H:%M:%S) [ab-train] $*" | tee -a "$L/queue.log"; }

$PY tune/build_dataset.py t5-abstain --system per-language --card card_v1c.md \
  --cap-template 8 --val-frac 0.1 --seed astcss-train-v1 --cards-dir train/cards-abstain \
  --extra-pairs workspace/trainset-t5/pairs.jsonl \
  --extra-pairs train/candidates/abstain-declinations.jsonl > "$L/build.log" 2>&1 \
  || { note "build failed: $(tail -3 "$L/build.log")"; exit 1; }
a=$($PY -c "import json;print(json.load(open('workspace/datasets/t5-langcard/manifest.json'))['rows']['train'])")
b=$($PY -c "import json;print(json.load(open('workspace/datasets/t5-abstain/manifest.json'))['rows']['train'])")
note "train rows: control $a   abstain-arm $b   (+$((b-a)) from 630 declination pairs)"
note "declination rows surviving the cap: $($PY -c "
import json
n=sum(1 for l in open('workspace/datasets/t5-abstain/train.jsonl')
      if json.loads(l)['messages'][-1]['content'].startswith('NONE:'))
print(n)")"

note "training one epoch"
$PY tune/train_qlora.py --base "$B08" --quant none --data workspace/datasets/t5-abstain \
  --out workspace/adapters/t5-abstain --epochs 1 --accum 16 --lr 2e-4 --seed 18 \
  --max-len 1024 > "$L/train.log" 2>&1
note "trained exit $? $(grep -E 'epoch [0-9] done' "$L/train.log" | tr '\n' ';')"

gen(){ local tag=$1 dir=$2 card=$3
  $PY tune/local_generate.py --base "$B08" --name "local:abtrain-$tag" --batch 8 --quant none \
    --out runs/abtrain-$tag --card $card --pairs-dir $dir --max-new-tokens 64 \
    --adapter workspace/adapters/t5-abstain/epoch1 > "$L/gen-$tag.log" 2>&1
  note "generated $tag"; }
gen abstain-lic   abstain   card_abstain.md
gen abstain-nolic abstain   card_pd.md
gen holdout       holdout   card_pd.md
gen eval_t5       eval_t5   card_t5.md

note "abstention 2x2"
SITTING_DUCK=$ENG ASTCSS_MACROS=$ENG/css_selectors-fix127.sql ASTCSS_EXEC_JOBS=6 \
  python3 abstain/score.py runs/abtrain-abstain-lic runs/abtrain-abstain-nolic 2>&1 | tee -a "$L/queue.log"
for d in holdout eval_t5; do
  SITTING_DUCK=$ENG ASTCSS_MACROS=$ENG/css_selectors-fix127.sql ASTCSS_EXEC_JOBS=8 \
    python3 qualify.py score --out runs/abtrain-$d --pairs-dir $d > "$L/score-$d.log" 2>&1
  note "$(printf '%-9s' $d) $(tail -n 1 "$L/score-$d.log" | cut -c1-96)"
done
note "done"
