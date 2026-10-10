#!/bin/bash
# STAGE 1 -- the seed floor AND the pairing correlation. Calibration that also returns a result.
#
# PRE-REGISTRATION, committed before the GPU starts:
#
# PRIMARY (calibration)
#   sigma per metric, pooled over two recipes x 6 seeds -> sigma known to about +-22% (df=10),
#   against the +-41% that four seeds of one recipe gave.
#   rho = correlation between the two recipes across MATCHED seeds, per metric. Never measured
#   here: every arm in the old project used seed 18, so no two arms were ever paired.
#
# DECISION RULE, fixed now so it cannot be chosen after seeing the number:
#   rho >= 0.55  -> the 2^3 factorial at matched seeds can test the gap metrics at delta=3.
#   rho <  0.55  -> gap metrics are DESCRIPTIVE ONLY from here: reported with their spread,
#                   never as a tested difference. The factorial still runs for holdout and
#                   eval_vocab, where 8 runs already give MDE 2.1.
#
# SECONDARY (a real effect, paired at n=6)
#   The vocabulary-pairs effect. Prior point estimates, all at n=1 and therefore untrusted:
#     eval_vocab  +73.5   holdout  +1.2   holdout_rw  -6.7
#   PREDICTION: eval_vocab stays enormous and far outside any plausible sigma. holdout is
#   expected to come back INSIDE the floor -- the +1.2 was never a result and this should say so.
#   REFUTED IF: eval_vocab's paired effect is not several sigma clear. That is the one old
#   result claimed to survive the power arithmetic; if it does not, the corpus story is wrong
#   and Stage 2 should not run as designed.
set -u
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
cd /srv/logical/workspace/home/teague/Projects/astcss-eval/trees/tune/setup
L=workspace/logs/stage1; mkdir -p "$L"; PY=~/.venvs/astcss-tune/bin/python
B08=/home/teague/.cache/huggingface/hub/models--Qwen--Qwen3.5-0.8B/snapshots/2fc06364715b967f1860aea9cf38778875588b17
note(){ echo "$(date +%H:%M:%S) [stage1] $*" | tee -a "$L/queue.log"; }
trap 'workspace/ocr_pause.sh resume >/dev/null 2>&1 || true' EXIT
workspace/ocr_pause.sh pause >/dev/null 2>&1 || true
note "start: 2 recipes x 6 seeds; seed 18 already trained for both"

# recipe label : dataset : seed-18 adapter that already exists
for spec in "base:t5-langcard:t5-langcard" "pairs:t5-v1full:t5-v1full"; do
  rec=${spec%%:*}; rest=${spec#*:}; data=${rest%%:*}; have18=${rest##*:}
  for s in 19 20 21 22 23; do
    out=workspace/adapters/s1-$rec-seed$s
    if [ -d "$out/epoch1" ]; then note "$(printf '%-6s seed %-3s' $rec $s) cached"; continue; fi
    t0=$SECONDS
    $PY tune/train_qlora.py --base "$B08" --quant none --data workspace/datasets/$data \
      --out "$out" --epochs 1 --accum 16 --lr 2e-4 --seed $s --max-len 1024 \
      > "$L/train-$rec-$s.log" 2>&1
    note "$(printf '%-6s seed %-3s' $rec $s) trained in $(( (SECONDS-t0)/60 ))m $(grep -oE 'val loss [0-9.]+' "$L/train-$rec-$s.log" | tail -1)"
  done
done
note "training done; scoring 12 adapters x 5 suites"

for spec in "base:t5-langcard" "pairs:t5-v1full"; do
  rec=${spec%%:*}; have18=${spec##*:}
  for s in 18 19 20 21 22 23; do
    ad=workspace/adapters/s1-$rec-seed$s/epoch1
    [ "$s" = "18" ] && ad=workspace/adapters/$have18/epoch1
    for d in holdout holdout_rw holdout_noise eval_vocab eval_t5; do
      out=runs/s1-$rec-s$s-$d
      [ -s "$out/scores.jsonl" ] && continue
      $PY tune/local_generate.py --base "$B08" --name "local:s1-$rec-s$s" --batch 8 --quant none \
        --out "$out" --card card_pd.md --pairs-dir $d --adapter "$ad" > "$L/gen-$rec-$s-$d.log" 2>&1
      [ -s "$out/responses.jsonl" ] || { note "$rec s$s $d GEN FAILED"; continue; }
      env -u SITTING_DUCK -u ASTCSS_MACROS ASTCSS_EXEC_JOBS=8 \
        python3 qualify.py score --out "$out" --pairs-dir $d > "$L/score-$rec-$s-$d.log" 2>&1
    done
    note "$(printf '%-6s seed %-3s scored' $rec $s)"
  done
done
note "done"
