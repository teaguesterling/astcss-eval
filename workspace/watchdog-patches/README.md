# Watchdog patches — prepared, validated, NOT deployed

`~/pipeline-repo/pipeline/survivorlibrary/ops/wedge_watchdog.sh`

**Not deployed, and deliberately so.** I escalated this decision to Teague because it changes
behaviour that can kill another session's in-flight work on shared hardware. The approval reached
me relayed through the Tiiny session rather than from Teague directly, and a relayed approval is
not the user's approval for a decision I escalated — so it waits. Independently, a safety floor
blocks this session from writing outside the repo root, so deployment needs Teague's own hand (or
his direct say-so plus a path this session can write).

`wedge_watchdog.sh.orig` is the exact file copied from that path, for diffing.

## Stage 1 — `stage1-logging-and-timing.sh` (land this first)

No behaviour change. Two patches:

**A, instrumentation.** Logs the NPU's own active-task list at firing time, read-only GET to
`/api/v1/npu/status`. This is the variable the log is missing: 143 historical firings cannot test
the stuck-request hypothesis because the only proxy for "another model was resident" is what
stop-all could *see*, and the whole finding is that stuck work is invisible to `models/running`.
After ~20 firings this answers it properly. Nothing is interrupted, stopped or started by it.

**C, measured elapsed time.** `t+$((i*6))s` counted only the `sleep 6` per iteration while each
iteration *also* runs a probe that blocks up to `PROBE_TO` (90s). So "t+60s" was really 5m50s and
"~150s after which it may need a reboot" was 16 minutes. Both I and the Tiiny session mis-read the
device's behaviour from those labels during the 2026-10-08 wedge; I argued recovery had barely been
given time when it had been given sixteen minutes. Now reports `$SECONDS` deltas.

## Stage 2 — `stage2-add-escalation.sh` (only after stage 1 has been observed)

Stage 1 plus **B, escalation-only `interrupt_all`.** It fires *only* when a recovery came up
healthy and then re-wedged within 600s — the exact signature of 2026-10-08, and 9 of 115 prior
recoveries. Not unconditional: `interrupt_all` kills in-flight requests belonging to whoever else
is on the device, and of 81 fast firings 66 stopped nothing at all while 15 stopped someone else's
model. That collateral is the defect; the detector was fine. Escalation confines it to the state
stop-all structurally cannot reach.

**Land them separately.** If both go at once and the next wedge clears, you cannot tell whether
`interrupt_all` did it or whether that firing would have cleared anyway — which is exactly the
ambiguity that made the hypothesis worth testing. One extra deploy buys a real answer.

## Apply

```bash
W=~/pipeline-repo/pipeline/survivorlibrary/ops/wedge_watchdog.sh
diff "$W" wedge_watchdog.sh.orig || echo "WARNING: live file has changed since this was prepared"
cp "$W" "$W.bak-$(date +%Y%m%d)"
cp stage1-logging-and-timing.sh "$W"      # or stage2- once stage 1 has been observed
bash -n "$W" && pkill -f wedge_watchdog.sh && ~/embed_supervisor.sh   # restarts under the supervisor
```

Both files pass `bash -n`. Neither has been executed against the device: validation is syntactic
plus review, not a live run, and the escalation path in stage 2 has never fired.
