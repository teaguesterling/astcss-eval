"""Declination training pairs: request -> `NONE: <what is missing>`.

WHY THIS SHOULD WORK WHERE THE LAST TWO BATCHES DID NOT. pseudo-d3 (55 pairs) and arity-a1
(36 pairs) were 0.3-0.5% nudges to behaviour the corpus ALREADY covered -- they had to outvote
existing signal and lost. Declination has zero representation: 0 of 8,326 training pairs and
0 of 536 eval pairs decline anything, and 0 of 33 unanswerable requests are declined by any
model under any card. A batch here teaches something rather than contradicting something.

TWO CATEGORIES ARE HELD OUT OF TRAINING ENTIRELY -- `history` and `dataflow` -- so the eval
separates two different claims:
    trained categories (25 of 33 eval pairs)   new phrasings, same concept  -> generalisation
    untrained categories (8 of 33)             concept never seen           -> transfer
Without that split a model could score 33/33 by keyword-matching "longer than" and "how many",
and we would call it abstention.

VARIETY IS THE POINT, NOT VOLUME. The register-collapse result (4B paraphrases wiped out the
interrogative register and cost 12 points on the holdout) says a batch drawn from few templates
teaches the templates. So each category carries many hand-written frames, in several registers
-- terse, imperative, interrogative, conversational -- and is instantiated over varied
quantities, nouns and identifiers.
"""
import json, os, random, sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LANGS = ["python", "javascript", "java", "go", "rust", "c", "cpp", "bash"]
FX = {"python": "py-lackpy", "javascript": "js-messe", "java": "java-rosetta",
      "go": "go-rosetta", "rust": "rs-magic", "c": "c-duckhts", "cpp": "cpp-duck-hunt",
      "bash": "sh-homelab"}

N = ["five", "ten", "twenty", "fifty", "a hundred", "three", "eight", "fifteen", "thirty"]
UNIT = ["lines", "statements", "characters", "bytes"]
THING = ["function", "method", "class", "module", "file", "helper", "routine"]
THINGS = {"function": "functions", "method": "methods", "class": "classes",
          "module": "modules", "file": "files", "helper": "helpers", "routine": "routines"}

#: category -> (reason text, [frames]). {t}=singular thing {ts}=plural {n}=number {u}=unit
CATS = {
 "size": ("needs line or size counts, which the language has no attribute for", [
   "{ts} longer than {n} {u}", "{ts} shorter than {n} {u}", "anything over {n} {u}",
   "the longest {t} here", "which {t} is biggest", "{ts} that run past {n} {u}",
   "short {ts}, under {n} {u}", "find the bulkiest {t}", "{ts} of more than {n} {u}",
   "is any {t} longer than {n} {u}?", "trim candidates: {ts} above {n} {u}",
   "the smallest {t} in the file", "{ts} between {n} and {n} {u}", "oversized {ts}",
   "how long is the biggest {t}", "anything that spans more than {n} {u}",
   "{ts} worth splitting up by length", "the chunkiest {t}", "{ts} under {n} {u} total"]),
 "count": ("needs counting or totals, which the language cannot express", [
   "classes with more than {n} methods", "files defining at least {n} {ts}",
   "how many {ts} are there", "{ts} containing fewer than {n} calls",
   "count the {ts} in each file", "classes declaring exactly {n} methods",
   "which file has the most {ts}", "modules with over {n} imports",
   "total number of {ts}", "{ts} that appear more than {n} times",
   "give me a tally of {ts}", "anything used at least {n} times",
   "{ts} with no more than {n} branches", "how often is each {t} called",
   "files with between {n} and {n} {ts}", "the {n} most common {ts}"]),
 "superlative": ("needs ranking across matches, which the language cannot express", [
   "the most-called {t}", "whichever {t} is used least", "the least referenced {t}",
   "rank the {ts} by how often they appear", "the single busiest {t}",
   "which {t} is called more than any other", "the top {n} {ts} by usage",
   "the most deeply nested {t}", "put the {ts} in order of popularity",
   "the runner-up {t} by call count", "the hottest {t} in this module",
   "least-used {ts} first", "sort {ts} from most to least referenced"]),
 "judgement": ("needs a judgement about quality or behaviour that is not in the tree", [
   "the slow {ts}", "badly named {ts}", "{ts} that need refactoring",
   "anything a reviewer would complain about", "poorly written {ts}",
   "{ts} that look fragile", "the ugly parts of this module",
   "which {ts} are hard to read", "{ts} with confusing names",
   "code that smells wrong", "{ts} that are probably buggy",
   "anything unidiomatic here", "{ts} worth rewriting", "the messy {ts}",
   "is this {t} well designed?", "{ts} a junior would struggle with",
   "{ts} that look thread-unsafe", "overly clever {ts}"]),
 "three-step": ("needs a chain of three combinator steps; the language takes exactly two", [
   "calls inside loops inside {ts}", "strings in conditionals in {ts}",
   "imports inside {ts} inside classes", "loops within conditionals within {ts}",
   "variables in comprehensions in {ts}", "returns inside try blocks inside {ts}",
   "calls in branches in the methods of a class",
   "members accessed in loops in {ts}", "throws inside catches inside {ts}"]),
 "runtime": ("needs runtime behaviour, which a static tree does not record", [
   "{ts} that allocate memory", "{ts} that touch the network",
   "{ts} that can block", "anything that writes to disk",
   "{ts} that spawn a thread", "which {ts} actually execute at import time",
   "{ts} that leak file handles", "code paths reachable at runtime",
   "{ts} that mutate global state at runtime", "{ts} using more than {n} megabytes",
   "{ts} that could deadlock", "what runs first when this loads"]),
}
HELD_OUT = ("history", "dataflow")   # never trained; the eval keeps 8 pairs in these


def main():
    rnd = random.Random("abstain-train-v1")
    rows, seen, i = [], set(), 0
    for cat, (reason, frames) in sorted(CATS.items()):
        for frame in frames:
            for _ in range(14):           # instantiate each frame many ways
                t = rnd.choice(THING)
                nl = (frame.replace("{ts}", THINGS[t]).replace("{t}", t)
                          .replace("{u}", rnd.choice(UNIT)))
                while "{n}" in nl:
                    nl = nl.replace("{n}", rnd.choice(N), 1)
                key = " ".join(nl.lower().split())
                if key in seen:
                    continue
                seen.add(key)
                i += 1
                lang = LANGS[i % len(LANGS)]
                rows.append({"id": "tr-%s-t5-ab%04d" % (lang, i), "tier": 5,
                             "fixture": FX[lang], "nl": nl, "paraphrases": [],
                             "css": "NONE: " + reason, "distractors": [], "treeql": None,
                             "abstain_category": cat,
                             "tags": ["abstain-train", "declination", "v0"]})
    p = os.path.join(HERE, "train/candidates/abstain-declinations.jsonl")
    with open(p, "w") as fh:
        for r in rows: fh.write(json.dumps(r) + "\n")
    import collections
    print("%d declination training pairs -> %s" % (len(rows), p))
    print("by category: %s" % dict(collections.Counter(r["abstain_category"] for r in rows)))
    print("held OUT of training entirely: %s" % (HELD_OUT,))
    print("distinct requests: %d" % len({r["nl"] for r in rows}))
    print("by language: %s" % dict(collections.Counter(r["id"].split("-")[1] for r in rows)))

if __name__ == "__main__":
    main()
