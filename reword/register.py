"""The register table: does each generator ADD a register, or restate the same one?

This is the check whose absence cost 12 points on the reworded holdout. One generator (the
4B) wiped out the interrogative register -- 45.5% of human paraphrases end in '?' against
0.1% of its output -- and nine generators all writing fluent declaratives would reproduce
that at nine times the cost.

Reference rows are the registers we already have, so each generator can be read as adding to
them or duplicating them:
    HUMAN paraphrases     the corpus today: long, 45% interrogative
    4B paraphrases        the arm that failed: terser, 0% interrogative
    holdout questions     hand-written: very terse, 60% imperative openers
"""
import json, glob, os, re, statistics, collections, sys

def stats(texts):
    if not texts: return None
    L = [len(t.split()) for t in texts]
    OPEN = ("take me to", "jump to", "show me", "find ", "where is", "which ", "list ", "get ")
    toks = [w for t in texts for w in re.findall(r"[a-z]{4,}", t.lower())]
    return {
      "n": len(texts),
      "words_med": statistics.median(L),
      "terse_pct": 100.0 * sum(1 for t in texts if len(t.split()) <= 4) / len(texts),
      "long_pct": 100.0 * sum(1 for t in texts if len(t.split()) >= 12) / len(texts),
      "quest_pct": 100.0 * sum(1 for t in texts if t.rstrip().endswith("?")) / len(texts),
      "imper_pct": 100.0 * sum(1 for t in texts if t.lower().startswith(OPEN)) / len(texts),
      "cap_pct": 100.0 * sum(1 for t in texts if t[:1].isupper()) / len(texts),
      "vocab": len(set(toks)),
      "ttr": len(set(toks)) / max(len(toks), 1),
    }

def show(label, s):
    if not s: print("  %-30s (none)" % label); return
    print("  %-30s %4d %6.0f %7.0f%% %7.0f%% %7.0f%% %7.0f%% %6.0f%% %6d %5.2f" % (
        label, s["n"], s["words_med"], s["terse_pct"], s["long_pct"], s["quest_pct"],
        s["imper_pct"], s["cap_pct"], s["vocab"], s["ttr"]))

def main():
    print("  %-30s %4s %6s %8s %8s %8s %8s %7s %6s %5s" % (
        "generator", "n", "wmed", "terse<=4", "long>=12", "quest?", "imper", "Capped", "vocab", "TTR"))
    # reference registers
    human, fourb = [], []
    for l in open("workspace/trainset-t5-rw/pairs.jsonl"):
        if not l.strip(): continue
        r = json.loads(l)
        if r.get("paraphrase_source", "").startswith("model"):
            fourb += r["paraphrases"]; human += (r.get("paraphrases_original") or [])
        else:
            human += (r.get("paraphrases") or [])
    show("REF human paraphrases", stats(human))
    show("REF 4B paraphrases (failed)", stats(fourb))
    show("REF holdout questions", stats([json.loads(l)["nl"] for l in
          open("holdout/pairs/accepted-holdout.jsonl") if l.strip()]))
    sample = {json.loads(l)["id"]: json.loads(l)["nl"] for l in open("reword/sample.jsonl") if l.strip()}
    show("REF the sample, as written", stats(list(sample.values())))
    print()
    for p in sorted(glob.glob("reword/out/*.jsonl")):
        rows = [json.loads(l) for l in open(p) if l.strip()]
        if not rows: print("  %-30s (empty)" % os.path.basename(p)[:-6]); continue
        show(rows[0]["generator"], stats([r["reworded"] for r in rows]))
    print("\n  wmed=median words  TTR=type/token ratio (lexical variety)")
    print("  A generator worth adding differs from the REF rows in SOME column.")

if __name__ == "__main__":
    main()
