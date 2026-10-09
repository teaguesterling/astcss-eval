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
# Direct :8800 socket. A THIRD projection: the only one carrying actual active_tasks objects.
# /api/v1/npu/status answers here and 404s through the vhost, where the proxied path is
# /api/v1/models/npu/status with a different shape entirely. Verified against the live device.
NPU_DIRECT="${TIINY_NPU:-http://192.168.4.144:8800/api/v1/npu/status}"
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
      # PATCH A (logging only, three read-only views). Every failure is reported with its HTTP
      # code and which view failed -- never one tidy "unreadable" line, which is how an instrument
      # reports nothing while looking like it worked.
      run_json="$(curl -s -m 10 -w '\n%{http_code}' -H "Authorization: Bearer $KEY" "$MGMT/models/running" 2>/dev/null)"
      npu_json="$(curl -s -m 10 -w '\n%{http_code}' -H "Authorization: Bearer $KEY" "$MGMT/models/npu/status" 2>/dev/null)"
      dir_json="$(curl -s -m 10 -w '\n%{http_code}' -H "Authorization: Bearer $KEY" "$NPU_DIRECT" 2>/dev/null)"
      FIRE_RUN="$run_json" FIRE_NPU="$npu_json" FIRE_DIR="$dir_json" python3 <<'PYFIRE' | while read -r l; do log "  $l"; done
import json, os
def view(name, blob):
    body, _, code = (blob or "").rpartition("\n")
    code = (code or "?").strip()
    if code != "200":
        return "%s: HTTP %s -- NOT MEASURED" % (name, code)
    try:
        d = json.loads(body)
    except Exception as e:
        return "%s: unparseable (%s) -- NOT MEASURED" % (name, type(e).__name__)
    if name == "running":
        inst = (d.get("instances") or {}).get("running") or []
        if not inst: return "running: no instances listed"
        return "running: " + "; ".join("%s active=%s npu=%s" % (
            i.get("model_id"), i.get("active_request_count"), i.get("npu_usage")) for i in inst)
    if name == "npu":
        return "npu: used=%s/%s available=%s" % (d.get("npu_used"), d.get("npu_total"), d.get("npu_available"))
    busy = [(m.get("model_name"), len(m.get("active_tasks") or []))
            for o in (d.get("occupants") or []) for m in (o.get("activate_model") or [])]
    if not busy: return "direct: no occupants"
    return "direct: " + "; ".join("%s tasks=%d" % t for t in busy)
for n, k in (("running","FIRE_RUN"), ("npu","FIRE_NPU"), ("direct","FIRE_DIR")):
    print(view(n, os.environ.get(k)))

# THE DISCRIMINATING SIGNAL. During the 2026-10-08 wedge, models/running listed only the
# embedder while interrupt_all later found five stuck requests across three chat models that
# were not listed at all. So no per-model view can be relied on to reveal this state. But
# npu_used is a DEVICE-level number and cannot be hidden by a model going unlisted: if it
# materially exceeds the sum of the listed instances' npu_usage, the difference is work the
# model views are not showing. Measured on a healthy device just now the two agree exactly
# (56 vs 1+55), so a gap is a real anomaly rather than normal slack.
try:
    rb, _, rc = (os.environ.get("FIRE_RUN") or "").rpartition("\n")
    nb, _, nc = (os.environ.get("FIRE_NPU") or "").rpartition("\n")
    if rc.strip() == "200" and nc.strip() == "200":
        inst = (json.loads(rb).get("instances") or {}).get("running") or []
        listed = sum(int(i.get("npu_usage") or 0) for i in inst)
        used = int(json.loads(nb).get("npu_used") or 0)
        gap = used - listed
        print("accounting: npu_used=%d listed_sum=%d gap=%+d%s" % (
            used, listed, gap,
            "  <-- UNACCOUNTED NPU: work not visible in any model view" if gap >= 5 else ""))
except Exception as e:
    print("accounting: NOT COMPUTED (%s)" % type(e).__name__)
PYFIRE
      running="$(printf '%s' "$run_json" | head -n -1 \
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
      # it must NOT run on every firing: 66 of 81 fast firings stopped nothing at all and 15
      # stopped someone else's model -- that collateral is the defect, not the detector. It runs
      # only on the signature that actually occurred: a cycle that came up HEALTHY and then
      # re-wedged inside 600s, which is 9 of 115 prior recoveries. That state means something is
      # stuck which stop-all structurally cannot reach.
      if [ "$ok" = 1 ]; then
        last_ok=$SECONDS
      elif [ "${last_ok:-0}" -gt 0 ] && [ $((SECONDS-last_ok)) -lt 600 ]; then
        log "  ESCALATING: recovered then re-wedged within $((SECONDS-last_ok))s -> interrupt_all"
        ia="$(curl -s -m 30 -w '\n%{http_code}' -X POST -H "Authorization: Bearer $KEY" "$MGMT/models/interrupt_all" 2>/dev/null)"
        log "  interrupt_all -> $(printf '%s' "$ia" | tr '\n' ' ' | cut -c1-160)"
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
