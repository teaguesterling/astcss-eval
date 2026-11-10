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
import json, os, time
now = time.time()

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
        # last_inference_time gives an AGE per listed instance at no extra call. Weaker than the
        # direct socket's per-task age -- a model holding stuck work may not be listed here at all,
        # which is the 2026-10-08 failure -- but free, and it distinguishes idle-resident from busy.
        def lag(i):
            li = i.get("last_inference_time")
            try: return "%+ds" % (now - float(li))
            except Exception: return "?"
        return "running: " + "; ".join("%s active=%s npu=%s last_inf=%s" % (
            i.get("model_id"), i.get("active_request_count"), i.get("npu_usage"), lag(i)) for i in inst)
    if name == "npu":
        return "npu: used=%s/%s available=%s" % (d.get("npu_used"), d.get("npu_total"), d.get("npu_available"))
    # AGE, not count. active_request_count=1 is indistinguishable from healthy work in flight,
    # which is exactly what a wedge looks like from outside; a task 900s old on a device that
    # answers nothing is unambiguous. Device-vs-local clock skew measured at ~1s on 2026-10-09,
    # so these ages are trustworthy. This endpoint enumerates TASKS, so it may show a model that
    # models/running omits -- the case that defeated every other view during the wedge.
    out, oldest = [], None
    for o in (d.get("occupants") or []):
        for m in (o.get("activate_model") or []):
            ages = []
            for tk in (m.get("active_tasks") or []):
                try: ages.append(now - float(tk.get("started_at")))
                except Exception: pass
            if ages:
                oldest = max(ages) if oldest is None else max(oldest, max(ages))
                out.append("%s tasks=%d oldest=%+ds" % (m.get("model_name"), len(ages), max(ages)))
            else:
                out.append("%s tasks=0" % m.get("model_name"))
    if not out: return "direct: no occupants"
    flag = "  <-- STUCK TASK (>300s)" if (oldest or 0) > 300 else ""
    return "direct: " + "; ".join(out) + flag
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
      fails=0
    fi
  fi
  sleep "$INTERVAL"
done
