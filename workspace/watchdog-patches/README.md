# Watchdog patches — prepared, validated against the live device, NOT deployed

`~/pipeline-repo/pipeline/survivorlibrary/ops/wedge_watchdog.sh`

**Not deployed.** I escalated this decision to Teague because it changes behaviour that can kill
another session's in-flight work on shared hardware. Approval reached me relayed through the Tiiny
session rather than from Teague directly, and a relayed approval is not the user's approval for a
decision I escalated. Independently, a safety floor blocks this session from writing outside the
repo root, so deployment needs Teague's own hand.

`wedge_watchdog.sh.orig` is the exact file copied from that path, for diffing.

## The first version of patch A was broken. This is the second.

The Tiiny session read it before applying anything and measured it against the device. It pointed
`TIINY_NPU` at `/api/v1/npu/status` on the **vhost**, which 404s, and parsed an
`occupants[].activate_model[].active_tasks` shape the vhost does not return. With a bare `except`
printing `unreadable`, it would have produced twenty tidy lines over twenty firings and concluded
nothing, while looking like instrumentation. That is the exact failure class this project has been
chasing all week, written by me, into the tool meant to detect it.

Verified directly, all three read-only:

```
p8800.api.tiiny/api/v1/npu/status          -> 404
p8800.api.tiiny/api/v1/models/npu/status   -> 200  {models[], npu_used, npu_total, npu_available}
p8800.api.tiiny/api/v1/models/running      -> 200  instances.running[] WITH active_request_count
192.168.4.144:8800/api/v1/npu/status       -> 200  HAS occupants[].activate_model[].active_tasks
```

One correction to the Tiiny session's report: the `occupants`/`active_tasks` shape **does** exist —
on the direct `:8800` socket, which is what `qualify.py`'s `TIINY_NPU` default targets. It is a
third projection, not a mistake. That also means `qualify.py`'s `ensure_loaded` busy-check works as
documented, which is what the earlier footprint evidence rested on.

## Stage 1 — `stage1-logging-and-timing.sh` (land first; contains no `interrupt_all` call)

**A, instrumentation.** Three read-only views at firing time, each reporting its own HTTP code and
failing loudly rather than collapsing into one word:

- `models/running` — per-instance `active_request_count` and `npu_usage`, parsed from a response
  the watchdog **already fetches** to decide what to stop. No new call, one fewer thing to 404.
- `models/npu/status` — `npu_used/npu_total/npu_available`.
- the direct `:8800` socket — the only view carrying actual `active_tasks` objects, logged as
  **age** rather than count: `oldest=+Ns` per model, flagged above 300s. A count of 1 is
  indistinguishable from healthy work in flight, which is exactly what a wedge looks like from
  outside; a task 900s old on a device answering nothing is unambiguous. This is the Tiiny
  session's suggestion and it is stronger than any count. Costs a fourth call and needs a route
  to the device address (`p8800` will not serve it), so it is best-effort with its own HTTP code
  and `NOT MEASURED` on failure.
- `models/running` also carries `last_inference_time`, so a per-instance **lag** comes free with no
  extra call — weaker (a model holding stuck work may not be listed at all, the 2026-10-08 case)
  but it distinguishes idle-resident from busy.

**Clock skew was checked before trusting ages.** `started_at` is a device epoch while the watchdog
computes `now` locally, so skew would manufacture fake ages. Measured 2026-10-09: a live embedding
task reads **+1.0s** old and the active embedder's `last_inference_time` lag reads **+1.5s**, against
an embed job doing ~12 units/s where live tasks are sub-second. So the clocks agree within about a
second and the ages are real. If the device is ever re-imaged or its NTP changes, re-check this
before reading an age as a stuck task.

**The accounting line is the part worth having.** During the 2026-10-08 wedge `models/running`
listed only the embedder while `interrupt_all` later found five stuck requests across three chat
models that were not listed at all — so no per-model view can be trusted to reveal this state, and
the Tiiny session is right that the instrumentation may simply not answer the question. But
`npu_used` is a **device-level** number and cannot be hidden by a model going unlisted. The patch
logs `npu_used` against the sum of listed instances' `npu_usage` and flags a gap of 5 or more as
unaccounted NPU. On a healthy device the two agree exactly (56 vs 1+55, measured), so a gap is a
real anomaly rather than normal slack. That invariant is the one signal that survives the failure
mode, and neither of us proposed it until the shapes were actually read.

**Expected-failure case, recorded so nobody misreads a clean log:** if every view shows nothing at
firing time and a later `interrupt_all` finds stuck work, **that is the finding** — the only thing
demonstrably able to see this state is `interrupt_all`'s own return value, and nothing read-only is.
A quiet log is not evidence of a quiet device.

**C, measured elapsed time.** `t+$((i*6))s` counted only the `sleep 6` per iteration while each
iteration also runs a probe blocking up to `PROBE_TO` (90s). So "t+60s" was really 5m50s and
"~150s, may need a reboot" was 16 minutes. Both sessions mis-read the wedge from those labels; I
argued recovery had barely been given time when it had been given sixteen minutes.

## Stage 2 — `stage2-add-escalation.sh` (only after stage 1 has been observed)

Stage 1 plus **B, escalation-only `interrupt_all`**, firing only when a recovery came up healthy
then re-wedged inside 600s — the 2026-10-08 signature, and 9 of 115 prior recoveries. Not
unconditional: of 81 fast firings 66 stopped nothing at all and 15 stopped someone else's model.
It also logs `interrupt_all`'s response, which is the only thing known to see the stuck state.

**Land them separately.** If both go at once and the next wedge clears, you cannot tell whether
`interrupt_all` did it or whether that firing would have cleared anyway.

## Validation actually performed

- both files pass `bash -n`
- `stage1` contains **no executable `interrupt_all`** (one mention, in a comment — checked)
- patch A's instrumentation block was **executed against the live device**, not just parsed:
  ```
  running: Qwen3-Embedding-0.6B active=1 npu=1 last_inf=+2s; Qwen3-30B-A3B-Instruct active=0 npu=55 last_inf=+17s
  npu: used=56/100 available=44
  direct: Qwen3-Embedding-0.6B tasks=1 oldest=+1s
  accounting: npu_used=56 listed_sum=56 gap=+0
  ```
- device-vs-local clock skew measured at ~1s, so the ages above are trustworthy
- the name list the recovery loop depends on still parses after the rewrite (the regression risk
  in splicing `-w %{http_code}` into a response that was previously piped raw)
- **stage 2's escalation path has never fired.** It cannot be tested without a wedge.

## Apply

```bash
W=~/pipeline-repo/pipeline/survivorlibrary/ops/wedge_watchdog.sh
diff "$W" wedge_watchdog.sh.orig || echo "WARNING: live file changed since this was prepared"
cp "$W" "$W.bak-$(date +%Y%m%d)"
cp stage1-logging-and-timing.sh "$W"
bash -n "$W" && pkill -f wedge_watchdog.sh && ~/embed_supervisor.sh
```
