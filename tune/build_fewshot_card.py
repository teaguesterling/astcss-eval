"""Build card_v1c_fewshot.md: card v1c, byte for byte, plus more EXAMPLES lines.

The only variable against card v1c is the extra examples (FINDINGS: every added prose
rule so far hurt the models that did well without it). Examples come from verified
training pairs only, never pairs/, and are picked one per FINDINGS error class:

  a node type written without a dot    assert_statement, conditional_expression
  #name as the bare name               .call#mkdir, .class#GitHubClient
  two steps, #name on the first        .class#WatchController .call, .try .throw
  :has returns the outer node          .fn:has(.call#...), .class:has(.fn#...), .try:has(.throw)

Left out on purpose, because each sits next to a known eval answer and would inflate
the result: with_statement and decorated_definition (eval tier-1 answers),
:has(.call#open) (the answer everyone gave on t4-p35), and .call#dumps (t2 "json dumps").

usage: python3 tune/build_fewshot_card.py [--out card_v1c_fewshot.md]
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import qualify  # noqa: E402

EXAMPLES = [
    ("every assert statement", "assert_statement"),
    ("every ternary conditional expression", "conditional_expression"),
    ("calls to mkdir", ".call#mkdir"),
    ("the class named GitHubClient", ".class#GitHubClient"),
    ("calls made inside the WatchController class", ".class#WatchController .call"),
    ("raises that happen inside a try block", ".try .throw"),
    ("functions that call execute", ".fn:has(.call#execute)"),
    ("functions that check isinstance", ".fn:has(.call#isinstance)"),
    ("classes that define validate", ".class:has(.fn#validate)"),
    ("try blocks that re-raise", ".try:has(.throw)"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "card_v1c_fewshot.md"))
    args = ap.parse_args()

    train = [json.loads(l) for f in sorted(glob.glob(os.path.join(HERE, "train/pairs/accepted-python-*.jsonl")))
             for l in open(f) if l.strip()]
    evals = [json.loads(l) for f in sorted(glob.glob(os.path.join(HERE, "pairs/*.jsonl")))
             if not os.path.basename(f).startswith("rejected-") for l in open(f) if l.strip()]
    ev_nl = {" ".join(t.lower().split()) for p in evals for t in [p.get("nl", "")] + (p.get("paraphrases") or [])}
    ev_css = {p["css"] for p in evals if p.get("css")}

    picked = []
    for nl, css in EXAMPLES:
        hits = [p for p in train if p["nl"] == nl and p["css"] == css]
        if not hits:
            sys.exit("not a verified python training pair: %r => %r" % (nl, css))
        if " ".join(nl.lower().split()) in ev_nl:
            sys.exit("example request is an eval request: %r" % nl)
        if css in ev_css:
            sys.exit("example selector is an eval answer: %r" % css)
        picked.append(hits[0])

    card = open(os.path.join(HERE, "card_v1c.md")).read()
    assert card.endswith("\n")
    lines = ["  %-44s%s" % (p["nl"], p["css"]) if len(p["nl"]) < 44 else "  %s  %s" % (p["nl"], p["css"])
             for p in picked]
    out = card + "\n".join(lines) + "\n"
    with open(args.out, "w") as fh:
        fh.write(out)

    leaked = qualify.leaked_ids(out, qualify.load_pairs())
    print("wrote %s (%d examples added, sha256 %s)" % (os.path.relpath(args.out, HERE), len(picked),
                                                        hashlib.sha256(out.encode()).hexdigest()[:12]))
    print("training ids: %s" % ", ".join(p["id"] for p in picked))
    print("leaked eval ids: %s" % (leaked or "none"))
    if leaked:
        sys.exit(1)


if __name__ == "__main__":
    main()
