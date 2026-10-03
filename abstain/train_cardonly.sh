#!/bin/bash
# The card-only control, which turns a confounded two-arm comparison into a clean three-way:
#
#   A  0.8b-t5-e1      original cards, no declinations        (exists)
#   B  t5-cardonly     LICENSED cards, no declinations        (this run)
#   C  t5-abstain      LICENSED cards + 553 declination rows  (running before this)
#
#   C vs B  isolates the declination ROWS
#   B vs A  isolates the CARD
#
# Identical to C's build in every argument except the declination --extra-pairs, and one epoch
# at seed 18 like both others, so the three differ only where intended.
set -u
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
cd /srv/logical/workspace/home/teague/Projects/astcss-eval/trees/tune/setup
while systemctl --user is-active astcss-abstain-train >/dev/null 2>&1; do sleep 60; done
L=$PWD/workspace/logs/abstain-train; mkdir -p "$L"; PY=~/.venvs/astcss-tune/bin/python
B08=/home/teague/.cache/huggingface/hub/models--Qwen--Qwen3.5-0.8B/snapshots/2fc06364715b967f1860aea9cf38778875588b17
ENG=/srv/logical/workspace/home/teague/Projects/astcss-eval/workspace/engine/sd-20260914-1835
note(){ echo "$(date +%H:%M:%S) [card-only] $*" | tee -a "$L/queue.log"; }

$PY tune/build_dataset.py t5-cardonly --system per-language --card card_v1c.md \
  --cap-template 8 --val-frac 0.1 --seed astcss-train-v1 --cards-dir train/cards-abstain \
  --extra-pairs workspace/trainset-t5/pairs.jsonl > "$L/build-cardonly.log" 2>&1 \
  || { note "build failed: $(tail -3 "$L/build-cardonly.log")"; exit 1; }
b=$($PY -c "import json;print(json.load(open('workspace/datasets/t5-cardonly/manifest.json'))['rows']['train'])")
note "train rows: $b (must equal the control's 15928 -- only the CARD differs)"
note "declination rows present: $($PY -c "
import json
print(sum(1 for l in open('workspace/datasets/t5-cardonly/train.jsonl')
          if json.loads(l)['messages'][-1]['content'].startswith('NONE:')))")"

$PY tune/train_qlora.py --base "$B08" --quant none --data workspace/datasets/t5-cardonly \
  --out workspace/adapters/t5-cardonly --epochs 1 --accum 16 --lr 2e-4 --seed 18 \
  --max-len 1024 > "$L/train-cardonly.log" 2>&1
note "trained exit $? $(grep -E 'epoch [0-9] done' "$L/train-cardonly.log" | tr '\n' ';')"

gen(){ local tag=$1 dir=$2 card=$3
  $PY tune/local_generate.py --base "$B08" --name "local:cardonly-$tag" --batch 8 --quant none \
    --out runs/cardonly-$tag --card $card --pairs-dir $dir --max-new-tokens 64 \
    --adapter workspace/adapters/t5-cardonly/epoch1 > "$L/gen-co-$tag.log" 2>&1; }
gen abstain-lic abstain card_abstain.md
gen holdout     holdout card_pd.md
gen eval_t5     eval_t5 card_t5.md
note "abstention 2x2 for the card-only arm"
SITTING_DUCK=$ENG ASTCSS_MACROS=$ENG/css_selectors-fix127.sql ASTCSS_EXEC_JOBS=6 \
  python3 abstain/score.py runs/cardonly-abstain-lic 2>&1 | tee -a "$L/queue.log"
for d in holdout eval_t5; do
  SITTING_DUCK=$ENG ASTCSS_MACROS=$ENG/css_selectors-fix127.sql ASTCSS_EXEC_JOBS=8 \
    python3 qualify.py score --out runs/cardonly-$d --pairs-dir $d > "$L/score-co-$d.log" 2>&1
  note "$(printf '%-9s' $d) $(tail -n 1 "$L/score-co-$d.log" | cut -c1-96)"
done
note "done"
