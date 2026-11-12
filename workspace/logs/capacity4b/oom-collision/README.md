# Why seeds 18-22 died in 4 minutes

Five of the six seeds OOM'd at weight-load time between 10:49:06 and 10:52:33 on
2026-10-25. The cause is not the memory budget. It is a collision with my own
calibration probe.

MEASURED, not inferred:

  probe4b2.log  last write 10:52:35, ending in its own CUDA OOM
  seed 22       last failure   10:52:33
  seed 23       loaded cleanly 10:53:47, and is still running

The probe that established the 704-token plateau (peak 8,664 -> 8,876 by step 2,
then +3 MiB over 48 further steps) was STILL HOLDING those ~8.9 GB when the
service started at 10:48:19. Two 8,146 MiB weight loads do not fit in 10.56 GiB.
Each seed got as far as tokenizing (`train rows 16288`) and died loading weights.
The probe and seed 22 killed each other; the GPU came free; seed 23 took it.

So the evidence for the budget still stands -- the probe proved the plateau, then
ate the queue. The fault is mine: I launched the queue without checking that the
GPU was free, with my own probe still on it.

capacity4b_retry.sh re-runs seeds 18-22 behind a gate that requires a free GPU.
These logs are kept as the record of the collision.
