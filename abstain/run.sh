#!/bin/bash
# Does granting license to decline change anything? Two cards, same models.
#   card_pd.md       "Reply with the selector only"  -- no license to decline
#   card_abstain.md  adds `NONE: <what is missing>` and lists what the language lacks
# Models: the 0.8B and the 9B, spanning the size range.
set -u
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
cd /srv/logical/workspace/home/teague/Projects/astcss-eval/trees/tune/setup
L=$PWD/workspace/logs/abstain; mkdir -p "$L"; PY=~/.venvs/astcss-tune/bin/python
H=/home/teague/.cache/huggingface/hub
B08=$H/models--Qwen--Qwen3.5-0.8B/snapshots/2fc06364715b967f1860aea9cf38778875588b17
B9=$H/models--Qwen--Qwen3.5-9B/snapshots/c202236235762e1c871ad0ccb60c8ee5ba337b9a
note(){ echo "$(date +%H:%M:%S) [abstain] $*" | tee -a "$L/queue.log"; }
go(){ local tag=$1 base=$2 ad=$3 b=$4 q=$5 card=$6
  $PY tune/local_generate.py --base "$base" --name "local:$tag" --batch $b --quant $q \
    --out runs/ab-$tag --card $card --pairs-dir abstain --adapter "$ad" \
    --max-new-tokens 64 > "$L/gen-$tag.log" 2>&1
  note "generated $tag ($(wc -l < runs/ab-$tag/responses.jsonl 2>/dev/null || echo 0) responses)"; }
note "no license to decline (card_pd)"
go 08-nolicense "$B08" workspace/adapters/t5-langcard/epoch1 8 none card_pd.md
go 9b-nolicense "$B9"  workspace/adapters/t5-9b-langcard/epoch2 2 4bit card_pd.md
note "with license to decline (card_abstain)"
go 08-license   "$B08" workspace/adapters/t5-langcard/epoch1 8 none card_abstain.md
go 9b-license   "$B9"  workspace/adapters/t5-9b-langcard/epoch2 2 4bit card_abstain.md
note "scoring the 2x2"
ENG=/srv/logical/workspace/home/teague/Projects/astcss-eval/workspace/engine/sd-20260914-1835
SITTING_DUCK=$ENG ASTCSS_MACROS=$ENG/css_selectors-fix127.sql ASTCSS_EXEC_JOBS=6 \
  python3 abstain/score.py runs/ab-08-nolicense runs/ab-9b-nolicense runs/ab-08-license runs/ab-9b-license 2>&1 | tee -a "$L/queue.log"
note "done"
