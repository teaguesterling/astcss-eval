#!/bin/bash
# Score models on the holdout validation suite.
#
# Card: card_pd.md, the language-neutral one. card_t5.md opens "over a Python code tree" and
# this suite spans eleven languages, so the Python card would confound every non-Python score.
#
# Models: the whole existing ladder, so the suite's first reading is a ladder on data no
# training has seen -- which is the point of building it.
set -u
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True   # the 9B OOMs without it
cd /srv/logical/workspace/home/teague/Projects/astcss-eval/trees/tune/setup
L=$PWD/workspace/logs/holdout; mkdir -p "$L"; PY=~/.venvs/astcss-tune/bin/python
ENG=/srv/logical/workspace/home/teague/Projects/astcss-eval/workspace/engine/sd-20260914-1835
H=/home/teague/.cache/huggingface/hub
B08=$H/models--Qwen--Qwen3.5-0.8B/snapshots/2fc06364715b967f1860aea9cf38778875588b17
B4=$H/models--Qwen--Qwen3.5-4B/snapshots/851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a
B9=$H/models--Qwen--Qwen3.5-9B/snapshots/c202236235762e1c871ad0ccb60c8ee5ba337b9a
note(){ echo "$(date +%H:%M:%S) [holdout] $*" | tee -a "$L/queue.log"; }
go(){ local tag=$1 base=$2 adapter=$3 batch=$4; shift 4
  out=runs/ho-$tag
  $PY tune/local_generate.py --base "$base" --name "local:$tag" --batch $batch \
    --out "$out" --card card_pd.md --pairs-dir holdout --adapter "$adapter" "$@" > "$L/gen-$tag.log" 2>&1
  SITTING_DUCK=$ENG ASTCSS_MACROS=$ENG/css_selectors-fix127.sql ASTCSS_EXEC_JOBS=8 \
    python3 qualify.py score --out "$out" --pairs-dir holdout > "$L/score-$tag.log" 2>&1
  note "$(printf '%-16s' $tag) $(tail -n 1 "$L/score-$tag.log" | cut -c1-100)"; }

note "scoring the ladder on the holdout suite"
go 0.8b-t5-e1 "$B08" workspace/adapters/t5-langcard/epoch1    8 --quant none
go 0.8b-base-e2 "$B08" workspace/adapters/ab-pd1-base/epoch2  8 --quant none
go 0.8b-pseudo-e2 "$B08" workspace/adapters/ab-pd1-plus/epoch2 8 --quant none
go 0.8b-arity-e2 "$B08" workspace/adapters/ab-arity/epoch2    8 --quant none
go 4b-t5-e2  "$B4" workspace/adapters/t5-4b-langcard/epoch2   4 --quant 4bit
go 9b-t5-e2  "$B9" workspace/adapters/t5-9b-langcard/epoch2   2 --quant 4bit
note "per-family and per-language breakdown"
python3 holdout/report.py 2>&1 | tee -a "$L/queue.log"
note "done"
