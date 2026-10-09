#!/usr/bin/env bash
# Tiiny NPU embedder wedge-watchdog.
# Probes the embedder via the stable bridge; on N consecutive failures it
# recovers the way that actually clears the wedge: stop ALL models (release the
# NPU) then start the embedder, and wait until it answers again.
#
# Run:  TIINY_AUTH_KEY=<key> setsid nohup bash wedge_watchdog.sh >/dev/null 2>&1 &
# Log:  ~/wedge_watchdog.log     Teardown: pkill -f wedge_watchdog.sh
set -uo pipefail
KEY="${TIINY_AUTH_KEY:?set TIINY_AUTH_KEY}"
MGMT="http://p8800.api.tiiny/api/v1"
NPU="${TIINY_NPU:-http://p8800.api.tiiny/api/v1/npu/status}"
EMB="http://api.tiiny/v1/embeddings"
EMBEDDER="Qwen/Qwen3-Embedding-0.6B"
LOG="$HOME/wedge_watchdog.log"
INTERVAL="${WD_INTERVAL:-30}"     # seconds between probes
FAILMAX="${WD_FAILMAX:-3}"        # consecutive fails before recovery
PROBE_TO="${WD_PROBE_TO:-12}"     # per-probe timeout

log(){ echo "[$(date '+%F %T')] $*" >> "$LOG"; }
probe(){ curl -s -m "$PROBE_TO" -o /dev/null -w '%{http_code}' -X POST \
  -H "Content-Type: application/json" -H "Authorization: Bearer $KEY" \
  -d "{\"model\":\"$EMBEDDER\",\"input\":\"ping\"}" "$EMB" 2>/dev/null; }

log "watchdog START (interval=${INTERVAL}s failmax=$FAILMAX probe_to=${PROBE_TO}s)"
fails=0
while true; do
  code="$(probe)"
  if [ "$code" = "200" ]; then
    [ "$fails" -gt 0 ] && log "recovered: probe 200 after $fails fail(s)"
    fails=0
  else
    fails=$((fails+1))
    log "probe FAIL (code=${code:-timeout}) ${fails}/${FAILMAX}"
    if [ "$fails" -ge "$FAILMAX" ]; then
      log "WEDGE DETECTED -> recovering (stop all models, start embedder)"
      # PATCH A (logging only): what the NPU itself says is busy, which models/running cannot see.
      npu="$(curl -s -m 15 -H "Authorization: Bearer $KEY" "$NPU" \
             | python3 -c 'import json,sys
try: n=json.load(sys.stdin)
except Exception: print("unreadable"); raise SystemExit
occ=n.get("occupants") or []
busy=[(m.get("model_name"),m.get("active_tasks")) for o in occ for m in (o.get("activate_model") or []) if m.get("active_tasks")]
print("; ".join("%s=%s" % t for t in busy) or "none")' 2>/dev/null)"
      log "  NPU active tasks at firing: ${npu:-unreadable}"
      running="$(curl -s -m 10 -H "Authorization: Bearer $KEY" "$MGMT/models/running" \
                 | python3 -c 'import json,sys;print(" ".join(json.load(sys.stdin).get("running",[])))' 2>/dev/null)"
      for m in $running; do
        curl -s -m 30 -X POST -H "Authorization: Bearer $KEY" "$MGMT/models/$m/stop" >/dev/null 2>&1
        log "  stopped $m"
      done
      sleep 5
      curl -s -m 30 -X POST -H "Authorization: Bearer $KEY" "$MGMT/models/$EMBEDDER/start" >/dev/null 2>&1
      log "  starting $EMBEDDER ..."
      ok=0
      t0=$SECONDS
      for i in $(seq 1 25); do
        sleep 6
        if [ "$(probe)" = "200" ]; then log "  embedder HEALTHY again (t+$((SECONDS-t0))s measured)"; ok=1; break; fi
      done
      [ "$ok" = 1 ] || log "  !! embedder still not healthy after $((SECONDS-t0))s measured (may need manual intervention / reboot)"

      # ---- PATCH B: escalation-only interrupt_all. ------------------------------------------
      # interrupt_all kills in-flight requests belonging to whoever else is using the device, so
      # it must NOT run on every firing: 66 of 81 fast firings stopped nothing at all, and 15
      # stopped someone else's model -- that collateral is the defect, not the detector. It runs
      # only on the signature that actually occurred: a cycle that came up HEALTHY and then
      # re-wedged. That state means something is stuck that stop-all structurally cannot reach.
      if [ "$ok" = 1 ]; then
        last_ok=$SECONDS
      elif [ "${last_ok:-0}" -gt 0 ] && [ $((SECONDS-last_ok)) -lt 600 ]; then
        log "  ESCALATING: recovered then re-wedged within $((SECONDS-last_ok))s -> interrupt_all"
        curl -s -m 30 -X POST -H "Authorization: Bearer $KEY" "$MGMT/models/interrupt_all" >/dev/null 2>&1
        log "  interrupt_all issued; stopping all and restarting the embedder once more"
        for m in $running; do
          curl -s -m 30 -X POST -H "Authorization: Bearer $KEY" "$MGMT/models/$m/stop" >/dev/null 2>&1
        done
        sleep 30
        curl -s -m 30 -X POST -H "Authorization: Bearer $KEY" "$MGMT/models/$EMBEDDER/start" >/dev/null 2>&1
        t1=$SECONDS
        for i in $(seq 1 25); do
          sleep 6
          if [ "$(probe)" = "200" ]; then log "  embedder HEALTHY after escalation (t+$((SECONDS-t1))s measured)"; break; fi
        done
        last_ok=0
      fi
      fails=0
    fi
  fi
  sleep "$INTERVAL"
done
