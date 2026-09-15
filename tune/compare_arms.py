"""Compare scored qualifier runs arm against arm, per model, on the pairs both answered.

usage: python3 tune/compare_arms.py BASE_DIR ARM_DIR [ARM_DIR ...]

Each DIR must already hold scores.jsonl (`qualify.py score --out DIR`, run under the
same engine for every arm -- a score is only comparable to one made by the same
engine). Leaked pairs, and pairs either arm failed to answer, are left out.

A card change is credited only against measured run-to-run noise: rerunning card v1
exactly (stage 3) flipped 1 of 98 matches for gemma and 6 of 98 for Coder. Flips
are printed next to the delta for that reason.
"""
import json
import os
import sys


def load(run_dir):
    rows = {}
    for line in open(os.path.join(run_dir, "scores.jsonl")):
        r = json.loads(line)
        rows[(r["model"], r["id"])] = r
    return rows


def main(base_dir, arm_dirs):
    base = load(base_dir)
    for arm_dir in arm_dirs:
        arm = load(arm_dir)
        print("\n%s  vs  %s" % (os.path.basename(arm_dir.rstrip("/")), os.path.basename(base_dir.rstrip("/"))))
        print("%-36s %4s %7s %7s %7s %6s %6s %6s  %s" % ("model", "n", "base", "arm", "delta", "+flip", "-flip",
                                                        "same", "by tier (base->arm)"))
        for model in sorted({m for m, _ in base} & {m for m, _ in arm}):
            ids = sorted(i for m, i in base if m == model and (model, i) in arm
                         and not base[(model, i)].get("leaked") and not arm[(model, i)].get("leaked")
                         and not base[(model, i)].get("error") and not arm[(model, i)].get("error"))
            if not ids:
                continue
            b = [base[(model, i)] for i in ids]
            a = [arm[(model, i)] for i in ids]
            bm, am = sum(r["exec_match"] for r in b), sum(r["exec_match"] for r in a)
            gained = sum(1 for x, y in zip(b, a) if y["exec_match"] and not x["exec_match"])
            lost = sum(1 for x, y in zip(b, a) if x["exec_match"] and not y["exec_match"])
            same = sum(1 for x, y in zip(b, a) if x.get("prediction") == y.get("prediction"))
            tiers = sorted({r["tier"] for r in b})
            by_tier = " ".join("T%d %d->%d/%d" % (t, sum(r["exec_match"] for r in b if r["tier"] == t),
                                                  sum(r["exec_match"] for r in a if r["tier"] == t),
                                                  sum(1 for r in b if r["tier"] == t)) for t in tiers)
            pct = lambda k: 100.0 * k / len(ids)  # noqa: E731
            print("%-36s %4d %6.1f%% %6.1f%% %+6.1f %6d %6d %6d  %s" % (
                model[:36], len(ids), pct(bm), pct(am), pct(am) - pct(bm), gained, lost, same, by_tier))
            for x, y in zip(b, a):
                if x["exec_match"] != y["exec_match"]:
                    print("    %s %-7s %-34s -> %-34s ref %s" % ("+" if y["exec_match"] else "-", x["id"],
                          (x.get("prediction") or "")[:34], (y.get("prediction") or "")[:34], x["reference"]))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2:])
