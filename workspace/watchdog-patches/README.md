# SUPERSEDED — do not apply these patches

The live file was rewritten between 2026-10-09 and 2026-11-01. **Applying the staged patches now
would be a regression.** They are moved to `superseded/` so nobody runs them. `wedge_watchdog.sh.orig`
(the file they were written against) is in there too, for diffing.

Target: `~/pipeline-repo/pipeline/survivorlibrary/ops/wedge_watchdog.sh`
Live copy as of 2026-11-09, for comparison: `wedge_watchdog.sh.live-2026-11-09`

## What the live file gained, and what that retires

Measured by diffing the live file against the staged original on 2026-11-09:

| Staged idea | Status in the live file |
|---|---|
| **C**, real elapsed time instead of `t+$((i*6))s` | **Done**, and better: it logs both `t+$((SECONDS-wait_start))s` and a separate `outage $((SECONDS-outage_start))s` that survives a failed recovery |
| **A**, stuck task reported as an AGE, never stopped | **Done** as `check_stuck`, with `WD_STUCK_WARN` (1800s), a sanitizer for device-reported strings, and a claude-inbox note |
| **A**, the NPU accounting invariant | **Absent.** The one surviving idea — see below |
| **B**, escalation-only `interrupt_all` | **Absent.** Never fired, never tested |

The live file also carries three things the patches did not have, and would have reverted:

- **401/403 handling.** "On 2026-11-01 this produced 102 false wedges." The staged patch treats a
  rejected key as a wedge and would restore all 102.
- **Embedder-only recovery**, with `WD_STOP_ALL=1` to opt back into stop-all. The staged patch
  restores unconditional stop-all, which took down other workstreams' models on 2026-10-04.
- **A key file, test hooks** (`WD_MAX_LOOPS`, `WD_*` overrides) and `test_wedge_watchdog.sh`.

## A correction to the old README, which was wrong by the time it mattered

The retired README recorded `p8800.api.tiiny/api/v1/npu/status -> 404` and concluded the `occupants`
shape lived only on the direct `:8800` socket. **That is no longer true.** Measured 2026-11-09:

```
p8800.api.tiiny/api/v1/npu/status          -> 200  keys: cpu,devices,hm_smi_available,memory,npu,occupants
p8800.api.tiiny/api/v1/models/npu/status   -> 200  keys: models,npu_available,npu_total,npu_used
p8800.api.tiiny/api/v1/models/running      -> 200  keys: instances,object,pending,running
```

The vhost now serves that route. So the live `check_stuck`, which calls `$MGMT/npu/status` and parses
`occupants[].activate_model[].active_tasks`, reads the shape it expects and works. I nearly reported
it as silent-failure instrumentation on the strength of a month-old measurement. The endpoint was
the thing to re-measure, not the code.

## The one idea worth keeping

Log `npu_used` against the sum of the listed instances' `npu_usage`, and flag a gap. It is the only
signal that survives the failure this watchdog exists for: during the 2026-10-08 wedge
`models/running` listed only the embedder, while a later `interrupt_all` found five stuck requests
across three chat models that were **not listed at all**. No per-model view can be trusted to reveal
that state. `npu_used` is device-level and cannot be hidden by a model going unlisted.

It agrees exactly on a healthy device, so a gap is an anomaly and not normal slack:

```
2026-10-09   npu_used=56  listed_sum=56  gap=+0   (1+55 across two instances)
2026-11-09   npu_used=1   listed_sum=1   gap=+0   (one instance)
```

Two sources, one line, no new HTTP call — the watchdog already fetches `models/running`, and
`models/npu/status` is one cheap read. Whoever owns this file should add it; it is four lines and
carries no behaviour change.

## Still unresolved, and deliberately so

Escalation-only `interrupt_all` (stage B) was never deployed and never fired. It changes behaviour
that can kill another session's in-flight work on shared hardware, and of 81 fast firings 66 stopped
nothing and 15 stopped someone else's model. It needs a fresh design against the current file, not a
revival of the staged one. The old reasoning is in `superseded/` if it is wanted.
