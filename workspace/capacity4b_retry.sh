#!/bin/bash
# CAPACITY, SEEDS 18-22. The other five seeds of the leg capacity4b.sh started.
#
# DO NOT EDIT WHILE RUNNING. A live edit of a running script here already cost the scoring phase
# of a 34-hour job: bash reads a script by byte offset and resumed mid-token.
#
# WHY THIS EXISTS. capacity4b.sh trained seed 23 and lost 18-22 to a GPU collision with my own
# calibration probe, which was still holding ~8.9 GB when the service started. The record and the
# timestamps that prove it are in workspace/logs/capacity4b/oom-collision/README.md. Nothing about
# the memory budget changed: seed 23 has held a 8,882 MiB peak for 540 steps.
#
# THE ONE NEW THING IS THE GATE. A seed does not start until capacity4b.service is gone AND the
# GPU reports room for a full load. The old queue had no such check, so five seeds burned in four
# minutes against a busy GPU and the loop recorded each as a failure and moved on. Absence of a
# free GPU is now a reason to wait, not a reason to proceed and fail.
#
# EVERYTHING ELSE IS IDENTICAL to capacity4b.sh by design -- same base, same dataset, same
# --quant none --accum 16 --lr 2e-4 --max-len 704 --epochs 2. The six seeds must differ only in
# the seed, or the leg does not measure capacity.
#
# The pre-registered prediction stands unchanged, in capacity4b.sh lines 22-30. It was recorded
# before any 4B number existed and is not restated here, so it cannot drift.
set -u
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
cd /srv/logical/workspace/home/teague/Projects/astcss-eval/trees/tune/setup
L=workspace/logs/capacity4b; mkdir -p "$L"; PY=~/.venvs/astcss-tune/bin/python
B4=/home/teague/.cache/huggingface/hub/models--Qwen--Qwen3.5-4B/snapshots/851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a
note(){ echo "$(date +%F' '%H:%M:%S) [retry] $*" | tee -a "$L/queue.log"; }

# AN IDLE GPU ON THIS BOX DOES NOT REPORT 11,264 MiB FREE. Measured 2026-10-25 while seed 23 ran:
#   total 11264   reserved 450   used 10548   free 268,  with the trainer itself at 9478
# so free-when-idle is 268 + 9478 = 9,746 MiB. The 450 MiB reserve and roughly 1,070 MiB of
# desktop and compositor memory never go away. My first draft of this gate required 9,800 free,
# which an idle GPU NEVER reports: every seed would have waited the full 48 h, logged SKIPPED, and
# the leg would have spent the week producing nothing. 9,000 separates idle (9,746) from occupied
# (268) with wide margin on both sides.
NEED=9000
# Belt and braces, and the sturdier of the two checks: no OTHER process may hold a 4B-scale
# allocation. The desktop clients sit at 33-102 MiB each, so a 1,024 MiB line tells a stray trainer
# apart from the desktop without depending on a free-memory figure at all.
BIG=1024
gate(){
  local waited=0 free hog
  while :; do
    if systemctl --user is-active --quiet astcss-cap4b.service; then
      [ $((waited % 1800)) -eq 0 ] && note "waiting: capacity4b.service still running (${waited}s)"
    else
      free=$(nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits 2>/dev/null)
      case "$free" in ''|*[!0-9]*) note "gate: cannot read GPU free memory"; return 1 ;; esac
      hog=$(nvidia-smi --query-compute-apps=pid,used_memory --format=csv,noheader,nounits 2>/dev/null \
            | awk -F", *" -v b="$BIG" '$2+0 >= b {print $1":"$2"MiB"}' | tr '\n' ' ')
      if [ -n "$hog" ]; then
        [ $((waited % 1800)) -eq 0 ] && note "waiting: another job holds the GPU: $hog (${waited}s)"
      elif [ "$free" -ge "$NEED" ]; then
        note "gate open: $free MiB free, no process over $BIG MiB"; return 0
      else
        [ $((waited % 1800)) -eq 0 ] && note "waiting: only $free MiB free, need $NEED (${waited}s)"
      fi
    fi
    [ $waited -ge 172800 ] && { note "gate TIMED OUT after 48h"; return 1; }
    sleep 60; waited=$((waited+60))
  done
}

# ocr_pause's own guard resumes the OCR once no holder is alive, so this script takes a hold and
# never calls `resume` -- that verb clears EVERY holder, including the other service's. The other
# service DOES call it on exit, so re-assert the hold on a timer.
workspace/ocr_pause.sh hold $$ || note "WARNING: OCR not paused"
( while kill -0 $$ 2>/dev/null; do sleep 600; workspace/ocr_pause.sh hold $$ >/dev/null 2>&1; done ) &

note "start: seeds 18-22, 4B, 2 epochs, --quant none --max-len 704, gated on a free GPU"

for s in 18 19 20 21 22; do
  out=workspace/adapters/cap4b-seed$s
  if [ -d "$out/epoch2" ]; then note "seed $s cached"; continue; fi
  for attempt in 1 2; do
    gate || { note "seed $s SKIPPED: gate never opened"; break; }
    t0=$SECONDS
    $PY tune/train_qlora.py --base "$B4" --quant none --data workspace/datasets/t5-v1full \
      --out "$out" --epochs 2 --accum 16 --lr 2e-4 --seed $s --max-len 704 \
      > "$L/train-$s.log" 2>&1
    if [ -d "$out/epoch2" ]; then
      note "seed $s trained in $(( (SECONDS-t0)/60 ))m $(grep -oE 'val loss [0-9.]+' "$L/train-$s.log" | tr '\n' ' ')"
      break
    fi
    note "seed $s attempt $attempt FAILED after $(( (SECONDS-t0)/60 ))m: $(grep -oE 'OutOfMemory|out of memory' "$L/train-$s.log" | head -1)$(tail -1 "$L/train-$s.log" | cut -c1-70)"
    cp "$L/train-$s.log" "$L/train-$s.attempt$attempt.log"
  done
done
note "training done; scoring epoch2 on five suites (seed 23 already scored by the first leg)"

for s in 18 19 20 21 22 23; do
  ad=workspace/adapters/cap4b-seed$s/epoch2
  [ -d "$ad" ] || { note "seed $s has no epoch2; nothing to score"; continue; }
  for d in holdout holdout_rw holdout_noise eval_vocab eval_t5; do
    out=runs/cap4b-s$s-$d
    [ -s "$out/scores.jsonl" ] && continue
    gate || { note "s$s $d SKIPPED: gate never opened"; break; }
    $PY tune/local_generate.py --base "$B4" --name "local:cap4b-s$s" --batch 2 --quant none \
      --out "$out" --card card_pd.md --pairs-dir $d --adapter "$ad" > "$L/gen-$s-$d.log" 2>&1
    [ -s "$out/responses.jsonl" ] || { note "s$s $d GEN FAILED"; continue; }
    env -u SITTING_DUCK -u ASTCSS_MACROS ASTCSS_EXEC_JOBS=8 \
      python3 qualify.py score --out "$out" --pairs-dir $d > "$L/score-$s-$d.log" 2>&1
  done
  note "seed $s scored"
done
note "done"
