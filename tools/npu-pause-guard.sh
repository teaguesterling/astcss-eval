#!/usr/bin/env bash
# npu-pause-guard.sh PID LEASE
# Resume PID (SIGCONT) as soon as LEASE is removed or has not been renewed for
# 10 minutes. Started by astcss-eval's qualify.py when it SIGSTOPs the NPU
# embedding job, so a harness that dies without resuming cannot leave it stopped.
PID="$1"; LEASE="$2"
[ -n "$PID" ] && [ -n "$LEASE" ] || { echo "usage: $0 PID LEASE" >&2; exit 2; }
while kill -0 "$PID" 2>/dev/null; do
  if [ ! -f "$LEASE" ] || [ $(( $(date +%s) - $(stat -c %Y "$LEASE") )) -ge 600 ]; then
    kill -CONT "$PID" 2>/dev/null
    rm -f "$LEASE"
    exit 0
  fi
  sleep 30
done
