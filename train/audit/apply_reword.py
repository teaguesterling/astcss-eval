"""Replace training request texts that do not determine their selector (the 2026-09-15 audit).

    python3 train/audit/apply_reword.py train/audit/reword-r1.json            # dry run
    python3 train/audit/apply_reword.py train/audit/reword-r1.json --apply    # write

A dry run lists every text audit_pairs.request_reasons flags in train/pairs/accepted-*.jsonl
with its replacement, and fails if a flagged text has no replacement, a replacement still
fails the gate, or a pair's texts stop being distinct.

--apply writes train/candidates/audit-r1.jsonl (ids <id>-a1; tier, fixture, css and
distractors unchanged) and moves each original out of its accepted file into
train/pairs/retired.jsonl, so pilot.py frees its node set. Then verify as usual:

    python3 pilot.py train/candidates/audit-r1.jsonl audit-r1 train --paraphrases=distinct
"""
import datetime
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, HERE)
import audit_pairs  # noqa: E402
import pilot  # noqa: E402


def main(argv):
    words_path = argv[0]
    apply = "--apply" in argv
    words = {k: v for k, v in json.load(open(words_path)).items() if not k.startswith("_")}
    batch = os.path.splitext(os.path.basename(words_path))[0].replace("reword-", "audit-")
    problems, revised, sources = [], [], {}
    for path in sorted(glob.glob(os.path.join(HERE, "train", "pairs", "accepted-*.jsonl"))):
        for line in open(path):
            p = json.loads(line)
            texts = [p["nl"]] + list(p["paraphrases"])
            flagged = {k: audit_pairs.request_reasons(p["css"], t, p["fixture"]) for k, t in enumerate(texts)}
            flagged = {k: v for k, v in flagged.items() if v}
            repl = {int(k): v for k, v in words.get(p["id"], {}).items()}
            if not flagged and not repl:
                continue
            for k in flagged:
                if k not in repl:
                    problems.append("%s text %d has no replacement: %r (%s)" % (p["id"], k, texts[k], flagged[k][0]))
            new = [repl.get(k, t) for k, t in enumerate(texts)]
            for k in repl:
                if k >= len(texts):
                    problems.append("%s: replacement for text %d, which doesn't exist" % (p["id"], k))
                    continue
                still = audit_pairs.request_reasons(p["css"], new[k], p["fixture"])
                if still:
                    problems.append("%s text %d replacement still fails: %r (%s)" % (p["id"], k, new[k], still[0]))
                print("%-24s %-44s %d: %s\n%-24s %-44s    -> %s" % (p["id"], p["css"][:44], k, texts[k], "", "", new[k]))
            cand = {"id": p["id"] + "-a1", "tier": p["tier"], "fixture": p["fixture"], "nl": new[0],
                    "paraphrases": new[1:], "css": p["css"], "distractors": p["distractors"], "treeql": p.get("treeql")}
            problems += ["%s: %s" % (p["id"], r) for r in pilot.static_reasons(cand, "distinct")]
            revised.append((p, cand, path))
            sources.setdefault(path, set()).add(p["id"])
    missing = set(words) - {p["id"] for p, _, _ in revised}
    problems += ["%s: in %s but not an accepted pair" % (i, words_path) for i in sorted(missing)]
    print("\n%d pairs revised, %d texts replaced" % (len(revised), sum(len(words.get(p["id"], {})) for p, _, _ in revised)))
    if problems:
        print("\nPROBLEMS (%d):" % len(problems))
        for m in problems:
            print("  " + m)
        return 1
    if not apply:
        print("dry run: nothing written (--apply to write)")
        return 0
    cand_path = os.path.join(HERE, "train", "candidates", "%s.jsonl" % batch)
    with open(cand_path, "w") as fh:
        for _, cand, _ in revised:
            fh.write(json.dumps(cand, ensure_ascii=False) + "\n")
    today = datetime.date.today().isoformat()
    with open(os.path.join(HERE, "train", "pairs", "retired.jsonl"), "a") as fh:
        for p, cand, _ in revised:
            fh.write(json.dumps(dict(p, retired=today, replaced_by=cand["id"],
                                     reason="request audit (FINDINGS.md): a request text did not determine the "
                                            "selector without the fixture; reworded as " + cand["id"]),
                                ensure_ascii=False) + "\n")
    for path, ids in sources.items():
        keep = [line for line in open(path) if json.loads(line)["id"] not in ids]
        with open(path + ".tmp", "w") as fh:
            fh.writelines(keep)
        os.replace(path + ".tmp", path)
    print("wrote %s; retired %d originals" % (os.path.relpath(cand_path, HERE), len(revised)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
