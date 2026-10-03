#!/bin/bash
# After the holdout ladder: reword every question with the 9B BASE model, then score the
# ladder again on the reworded sets. Serialised because both want the GPU.
#
# Two suites get reworded: the holdout (323) and eval_t5 (118). eval_t5 matters most here --
# it is the headline, and if its scores hold under rewording then they are measuring selector
# skill rather than familiar phrasing; if they fall, the headline has been flattering us all
# along and every number in FINDINGS needs that caveat.
set -u
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
cd /srv/logical/workspace/home/teague/Projects/astcss-eval/trees/tune/setup
while systemctl --user is-active astcss-holdout-run >/dev/null 2>&1; do sleep 60; done
L=$PWD/workspace/logs/holdout; PY=~/.venvs/astcss-tune/bin/python
ENG=/srv/logical/workspace/home/teague/Projects/astcss-eval/workspace/engine/sd-20260914-1835
H=/home/teague/.cache/huggingface/hub
B08=$H/models--Qwen--Qwen3.5-0.8B/snapshots/2fc06364715b967f1860aea9cf38778875588b17
B9=$H/models--Qwen--Qwen3.5-9B/snapshots/c202236235762e1c871ad0ccb60c8ee5ba337b9a
note(){ echo "$(date +%H:%M:%S) [reword] $*" | tee -a "$L/queue.log"; }

note "rewording holdout (323) with the 9B base"
$PY holdout/reword.py --pairs-dir holdout --out holdout_rw --batch 4 > "$L/reword-holdout.log" 2>&1
note "$(grep -E '^kept|^rejected' "$L/reword-holdout.log" | tr '\n' ' ')"
note "rewording eval_t5 (118)"
$PY holdout/reword.py --pairs-dir eval_t5 --out eval_t5_rw --batch 4 > "$L/reword-t5.log" 2>&1
note "$(grep -E '^kept|^rejected' "$L/reword-t5.log" | tr '\n' ' ')"

score(){ local tag=$1 dir=$2 base=$3 adapter=$4 batch=$5 quant=$6
  out=runs/rw-$tag-$dir
  $PY tune/local_generate.py --base "$base" --name "local:rw-$tag" --batch $batch --quant $quant \
    --out "$out" --card card_pd.md --pairs-dir $dir --adapter "$adapter" > "$L/gen-rw-$tag-$dir.log" 2>&1
  SITTING_DUCK=$ENG ASTCSS_MACROS=$ENG/css_selectors-fix127.sql ASTCSS_EXEC_JOBS=8 \
    python3 qualify.py score --out "$out" --pairs-dir $dir > "$L/score-rw-$tag-$dir.log" 2>&1
  note "$(printf '%-14s %-12s' $tag $dir) $(tail -n 1 "$L/score-rw-$tag-$dir.log" | cut -c1-96)"; }

for dir in holdout_rw eval_t5_rw; do
  [ -f $dir/pairs/accepted-rw.jsonl ] || { note "$dir missing; skipping"; continue; }
  score 0.8b-t5-e1 $dir "$B08" workspace/adapters/t5-langcard/epoch1 8 none
  score 9b-t5-e2   $dir "$B9"  workspace/adapters/t5-9b-langcard/epoch2 2 4bit
done
note "done"
