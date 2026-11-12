"""Score a fluent-mutation adapter on held-out rows and on the hand-written reference set.

    python3 mutator/score_fluent.py --base <base> --adapter workspace/adapters/fluent-4b/epoch1 \
        --name fluent-4b-e1 --quant 4bit --out runs/fluent-4b-e1 --limit 300

Two evals, because they answer different questions:

  held  -- `val.jsonl` from workspace/datasets/fluent-mutations, never trained on. Same
           distribution as training (mined edits), so it measures whether the grammar was learned
           at all. Each row carries its OWN system prompt, which is what it was trained with --
           the corpus has two card variants (9282 / 2268 rows) and substituting one card for both
           would confound the card with the model.
  ref   -- mutator/tasks.json, 20 tasks written by hand before any of this was trained. Comparable
           to the cold spot tests (the untrained 9B scored 8/20), and out of distribution.

WHY NOT judge.judge() FOR THE BUCKETS: its `OPS` set is stale against the corpus the adapters were
actually trained on. `OPS` has 13 ops and lists `setCondition`; the corpus's most common op is
`replaceWith`, which is absent, and it uses `addCondition`, `evalSnippet`, `insertBefore`,
`coveringTests`, `backwardSlice` and a dozen more. Every one of those would be bucketed
"malformed" however perfect the answer. So the op vocabulary here is derived from the corpus, and
the bucket means "did it parse and use an op the corpus teaches". judge.score() is used unchanged
-- it parses both sides and compares, and never consults OPS.

Scored per part (selector / op / args) for the reason the surface study was: the argument is
partly transcribed from the request, so one combined number is inflated next to the selector evals.
"""
import argparse
import collections
import json
import os
import random
import re
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tune"))
sys.path.insert(0, os.path.join(HERE, "mutator"))

import prompting                      # noqa: E402
import judge as J                     # noqa: E402

DATA = os.path.join(HERE, "workspace/datasets/fluent-mutations")
_OP = re.compile(r"\)\s*\.\s*([A-Za-z_]\w*)\s*\(")


def corpus_ops(path, floor=5):
    """The op vocabulary the adapter was actually trained on, with a floor so a single
    mis-mined row does not widen it."""
    c = collections.Counter()
    for line in open(path):
        a = next(m["content"] for m in json.loads(line)["messages"] if m["role"] == "assistant")
        m = _OP.search(a)
        if m:
            c[m.group(1)] += 1
    return {k for k, v in c.items() if v >= floor}, c


def held_rows(limit, seed):
    rows = []
    for line in open(os.path.join(DATA, "val.jsonl")):
        ms = json.loads(line)["messages"]
        rows.append({"system": next((m["content"] for m in ms if m["role"] == "system"), None),
                     "request": next(m["content"] for m in ms if m["role"] == "user"),
                     "call": next(m["content"] for m in ms if m["role"] == "assistant")})
    if limit and limit < len(rows):
        random.Random(seed).shuffle(rows)
        rows = rows[:limit]
    for i, r in enumerate(rows):
        r["id"] = "held-%04d" % i
    return rows


def corpus_card():
    """The system prompt the MAJORITY of training rows carried. Needed as a control: the ref suite
    normally uses mutator/card.py's card, which no training row ever saw, so a trained model doing
    badly there could be card mismatch rather than a failure to generalise."""
    c = collections.Counter()
    for line in open(os.path.join(DATA, "train.jsonl")):
        ms = json.loads(line)["messages"]
        c[next((m["content"] for m in ms if m["role"] == "system"), "")] += 1
    return c.most_common(1)[0][0]


def ref_rows(use_corpus_card=False):
    spec = json.load(open(os.path.join(HERE, "mutator/tasks.json")))
    if use_corpus_card:
        card = corpus_card()
    else:
        from card import build as build_card
        card = build_card()
    return [{"id": t["id"], "system": card, "request": t["request"], "call": t["call"]}
            for t in spec["tasks"]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--adapter")
    ap.add_argument("--name", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--eval", default="held,ref")
    ap.add_argument("--ref-corpus-card", action="store_true",
                    help="give the ref suite the card the training rows carried (card control)")
    ap.add_argument("--limit", type=int, default=300, help="held-out rows (0 = all 1284)")
    ap.add_argument("--seed", type=int, default=18)
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--max-new-tokens", type=int, default=128)
    ap.add_argument("--quant", choices=("4bit", "none"), default="4bit")
    ap.add_argument("--embed-cpu", action="store_true")
    args = ap.parse_args()

    import torch
    from transformers import AutoTokenizer
    from train_qlora import load_model

    ops, counts = corpus_ops(os.path.join(DATA, "train.jsonl"))
    print("corpus op vocabulary: %d ops (top: %s)"
          % (len(ops), ", ".join(k for k, _ in counts.most_common(6))), flush=True)

    suites = {}
    if "held" in args.eval:
        suites["held"] = held_rows(args.limit, args.seed)
    if "ref" in args.eval:
        suites["ref"] = ref_rows(args.ref_corpus_card)

    os.makedirs(args.out, exist_ok=True)
    json.dump({"started": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "models": [args.name],
               "runner": "local", "base": args.base, "adapter": args.adapter,
               "quant": args.quant, "limit": args.limit, "seed": args.seed,
               "suites": {k: len(v) for k, v in suites.items()},
               "corpus_ops": sorted(ops), "ref_corpus_card": args.ref_corpus_card, "prompt_format": prompting.FORMAT_VERSION},
              open(os.path.join(args.out, "meta.json"), "w"), indent=2)

    tok = AutoTokenizer.from_pretrained(args.base)
    tok.padding_side = "left"
    model, dev = load_model(args.base, args.embed_cpu, args.quant)
    if args.adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, args.adapter)
    model.eval()
    pad = tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id
    stop_ids = sorted({i for i in (tok.convert_tokens_to_ids(prompting.end_of_turn(tok)),
                                   tok.eos_token_id,
                                   getattr(model.generation_config, "eos_token_id", None))
                       if isinstance(i, int)})

    summary = []
    with open(os.path.join(args.out, "responses.jsonl"), "w") as fh:
        for suite, rows in suites.items():
            t = collections.Counter()
            for i in range(0, len(rows), args.batch):
                chunk = rows[i:i + args.batch]
                texts = [prompting.prompt_text(tok, r["system"], r["request"]) for r in chunk]
                enc = tok(texts, return_tensors="pt", padding=True,
                          add_special_tokens=False).to(dev)
                t0 = time.time()
                with torch.no_grad():
                    out = model.generate(**enc, max_new_tokens=args.max_new_tokens,
                                         do_sample=False, pad_token_id=pad, eos_token_id=stop_ids)
                dt = (time.time() - t0) / len(chunk)
                for r, seq in zip(chunk, out):
                    raw = tok.decode(seq[enc["input_ids"].shape[1]:], skip_special_tokens=True)
                    pred = raw.strip().splitlines()[0].strip() if raw.strip() else ""
                    got = J.parse(pred)
                    sc = J.score({"call": r["call"]}, got)
                    bucket = ("ok" if got and got["op"] in ops else
                              "unknown_op" if got else
                              "wrong_surface" if re.match(r"^\s*[.#]\w", pred) or "{" in pred
                              else "malformed")
                    t[bucket] += 1
                    for k in ("selector", "op", "args", "all"):
                        t[k] += 1 if sc[k] else 0
                    t["n"] += 1
                    fh.write(json.dumps({"model": args.name, "suite": suite, "id": r["id"],
                                         "request": r["request"], "raw": raw, "prediction": pred,
                                         "reference": r["call"], "bucket": bucket, "score": sc,
                                         "latency_s": round(dt, 2)}, ensure_ascii=False) + "\n")
            n = max(t["n"], 1)
            line = ("%-5s n=%-4d parse_ok %5.1f%%  unknown_op %3d  malformed %3d  wrong_surface %3d"
                    "  |  selector %5.1f%%  op %5.1f%%  args %5.1f%%  ALL %5.1f%%"
                    % (suite, t["n"], 100 * t["ok"] / n, t["unknown_op"], t["malformed"],
                       t["wrong_surface"], 100 * t["selector"] / n, 100 * t["op"] / n,
                       100 * t["args"] / n, 100 * t["all"] / n))
            print(line, flush=True)
            summary.append({"suite": suite, **{k: t[k] for k in
                            ("n", "ok", "unknown_op", "malformed", "wrong_surface",
                             "selector", "op", "args", "all")}})
    json.dump(summary, open(os.path.join(args.out, "summary.json"), "w"), indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
