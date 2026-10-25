#!/bin/bash
# CAPACITY: does 4B change what the corpus can teach? The one factor the factorial would add.
#
# DO NOT EDIT WHILE RUNNING. A live edit of a running script here already cost the scoring phase
# of a 34-hour job: bash reads a script by byte offset and resumed mid-token.
#
# WHY ONLY THIS. Of the three factors in the planned 2^3, two are settled: the vocabulary pairs at
# +74.2 (t=51.7, two independent six-seed replications) and card dependence at 28.4 against 1.8
# points on identical weights. Capacity is unanswered, and the earlier attempt was confounded --
# a 4-bit 9B scored 11 points BELOW an unquantised 0.8B, which measures quantisation, not size.
#
# PRECISION IS MATCHED, AND THAT IS THE POINT. Both sides run --quant none. The 4B does not fit at
# --max-len 1024 (measured: peak 8,664 MiB then CUDA OOM needing 12 MiB more). It fits at 704 with
# a plateau: peak 8,664 -> 8,876 by step 2, then +3 MiB across 48 further steps.
#
# THE TRIM CHANGES NO GRADIENT. train_qlora.py:57 is `ids = (prompt_ids + answer_ids)[-max_len:]`,
# a truncation cap, not padding. Encoded data is median 580 tokens, max 670, identical under both
# tokenizers at both caps. 670 < 704, so no row is truncated either way. Verified, not assumed.
#
# THE 0.8B SIDE ALREADY EXISTS: s1b-pairs-seed{18..23}/epoch2, same dataset, same recipe, 2 epochs,
# --quant none. This leg adds only the 4B half.
#
# PREDICTION, recorded before the GPU starts:
#   eval_vocab holds at or above the 0.8B's 85%. The constructs are learnable at 0.8B, so capacity
#     should not remove them.
#   holdout rises. More parameters on the same data, and the 0.8B sits at 75.7%.
#   holdout_rw and holdout_noise are the real question. No corpus intervention has moved either.
#     If capacity moves them, the remaining gaps are a size limit. If it does not, they are a
#     property of the task or the suites, and no amount of training data will reach them.
#   REFUTED IF: eval_vocab at 4B falls materially below 85%. That would make the pairs' benefit
#     size-specific, which would be surprising and would change what we ship.
#
# Generation batch is 2 for the 4B against 8 for the 0.8B. Greedy decoding is deterministic per
# sequence, so batch changes throughput and not output -- unlike training batch, which is fixed.
set -u
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
cd /srv/logical/workspace/home/teague/Projects/astcss-eval/trees/tune/setup
L=workspace/logs/capacity4b; mkdir -p "$L"; PY=~/.venvs/astcss-tune/bin/python
B4=/home/teague/.cache/huggingface/hub/models--Qwen--Qwen3.5-4B/snapshots/851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a
note(){ echo "$(date +%F' '%H:%M:%S) [cap4b] $*" | tee -a "$L/queue.log"; }
trap 'workspace/ocr_pause.sh resume >/dev/null 2>&1' EXIT
workspace/ocr_pause.sh hold $$ || note "WARNING: OCR not paused"
note "start: 4B, 6 seeds, 2 epochs, --quant none --max-len 704"

for s in 18 19 20 21 22 23; do
  out=workspace/adapters/cap4b-seed$s
  if [ -d "$out/epoch2" ]; then note "seed $s cached"; continue; fi
  t0=$SECONDS
  $PY tune/train_qlora.py --base "$B4" --quant none --data workspace/datasets/t5-v1full \
    --out "$out" --epochs 2 --accum 16 --lr 2e-4 --seed $s --max-len 704 \
    > "$L/train-$s.log" 2>&1
  if [ ! -d "$out/epoch2" ]; then
    note "seed $s TRAIN FAILED: $(grep -oE 'OutOfMemory|out of memory' "$L/train-$s.log" | head -1)$(tail -1 "$L/train-$s.log" | cut -c1-70)"
    continue
  fi
  note "seed $s trained in $(( (SECONDS-t0)/60 ))m $(grep -oE 'val loss [0-9.]+' "$L/train-$s.log" | tr '\n' ' ')"
done
note "training done; scoring epoch2 on five suites"

for s in 18 19 20 21 22 23; do
  ad=workspace/adapters/cap4b-seed$s/epoch2
  [ -d "$ad" ] || continue
  for d in holdout holdout_rw holdout_noise eval_vocab eval_t5; do
    out=runs/cap4b-s$s-$d
    [ -s "$out/scores.jsonl" ] && continue
    $PY tune/local_generate.py --base "$B4" --name "local:cap4b-s$s" --batch 2 --quant none \
      --out "$out" --card card_pd.md --pairs-dir $d --adapter "$ad" > "$L/gen-$s-$d.log" 2>&1
    [ -s "$out/responses.jsonl" ] || { note "s$s $d GEN FAILED"; continue; }
    env -u SITTING_DUCK -u ASTCSS_MACROS ASTCSS_EXEC_JOBS=8 \
      python3 qualify.py score --out "$out" --pairs-dir $d > "$L/score-$s-$d.log" 2>&1
  done
  note "seed $s scored"
done
note "done"
