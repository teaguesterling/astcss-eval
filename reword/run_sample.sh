#!/bin/bash
# Register probe on 120 queries. Hosted and device generators only -- the ollama models
# contend with the training arms for VRAM and go after they finish.
# The Tiiny serves ONE model at a time, so its two run sequentially.
set -u
cd /srv/logical/workspace/home/teague/Projects/astcss-eval/trees/tune/setup
L=workspace/logs/reword; mkdir -p "$L"
note(){ echo "$(date +%H:%M:%S) [reword] $*" | tee -a "$L/queue.log"; }
for g in claude:haiku claude:sonnet; do
  note "start $g"
  python3 reword/generate.py --gen "$g" --batch 20 > "$L/$(echo $g | tr ':/' '__').log" 2>&1
  note "$(tail -1 "$L/$(echo $g | tr ':/' '__').log")"
done
for g in "tiiny:Qwen/Qwen3-30B-A3B-Instruct" "tiiny:openai/gpt-oss-20b"; do
  note "start $g (device, sequential)"
  python3 reword/generate.py --gen "$g" --batch 20 > "$L/$(echo $g | tr ':/' '___').log" 2>&1
  note "$(tail -1 "$L/$(echo $g | tr ':/' '___').log")"
done
note "done"
