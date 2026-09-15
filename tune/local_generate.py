"""Ask a local model (optionally with a LoRA adapter) the eval requests, qualifier-style.

usage: ~/.venvs/astcss-tune/bin/python tune/local_generate.py --base PATH --out runs/DIR --name LABEL
           [--adapter DIR] [--card card_v1c.md | --card none] [--retrieve K [--retrieve-portable]]
           [--per-tier 0] [--seed qualify-v1] [--batch 8]

Writes DIR/responses.jsonl and DIR/meta.json in qualify.py's format, so
`python3 qualify.py score --out DIR` and tune/compare_arms.py work unchanged.

The prompt is built by tune/prompting.py, the same function the trainer uses, so a model
is always asked in exactly the format it was trained on. Greedy decoding, thinking off.
The 2080 Ti has no bfloat16, so compute is float16; the 248k-vocab embedding table stays
on the CPU (see tune/smoke_qlora.py for the memory accounting).
"""
import argparse
import hashlib
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tune"))
import qualify  # noqa: E402
import prompting  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--adapter")
    ap.add_argument("--name", required=True, help="model label written to every row")
    ap.add_argument("--out", required=True)
    ap.add_argument("--card", default="card_v1c.md", help="system prompt file, or 'none'")
    ap.add_argument("--retrieve", type=int, default=0)
    ap.add_argument("--retrieve-portable", action="store_true")
    ap.add_argument("--per-tier", type=int, default=0)
    ap.add_argument("--seed", default="qualify-v1")
    ap.add_argument("--batch", type=int, default=8)
    ap.add_argument("--max-new-tokens", type=int, default=48)
    args = ap.parse_args()

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    card = None if args.card == "none" else open(os.path.join(HERE, args.card)).read()
    pairs = qualify.sample(qualify.load_pairs(), args.per_tier, args.seed)
    contexts = {p["id"]: (card, []) for p in pairs}
    if args.retrieve:
        import context as ctx
        retriever = ctx.Retriever(langs=("python",), other_portable=args.retrieve_portable)
        for p in pairs:
            ex = retriever.nearest(p["nl"], args.retrieve, exclude_css={p["css"]})
            contexts[p["id"]] = (ctx.with_examples(card or "", ex), [e["id"] for e in ex])
    leaks = sorted({i for p in pairs if contexts[p["id"]][0] for i in qualify.leaked_ids(contexts[p["id"]][0], [p])})

    os.makedirs(args.out, exist_ok=True)
    resp_path = os.path.join(args.out, "responses.jsonl")
    done = set()
    if os.path.exists(resp_path):
        done = {json.loads(l)["id"] for l in open(resp_path) if l.strip() and not json.loads(l).get("error")}
    meta_path = os.path.join(args.out, "meta.json")
    if not os.path.exists(meta_path):
        json.dump({"started": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "models": [args.name], "runner": "local",
                   "base": args.base, "adapter": args.adapter, "per_tier": args.per_tier, "seed": args.seed,
                   "pair_ids": [p["id"] for p in pairs], "card": args.card,
                   "card_sha256": hashlib.sha256(card.encode()).hexdigest() if card else None,
                   "retrieve": args.retrieve, "retrieve_portable": args.retrieve_portable,
                   "leaked_ids": leaks, "prompt_format": prompting.FORMAT_VERSION},
                  open(meta_path, "w"), indent=2)

    tok = AutoTokenizer.from_pretrained(args.base)
    tok.padding_side = "left"
    bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.float16,
                             bnb_4bit_use_double_quant=True, llm_int8_enable_fp32_cpu_offload=True)
    model = AutoModelForCausalLM.from_pretrained(args.base, quantization_config=bnb, dtype=torch.float16,
                                                 device_map={"model.embed_tokens": "cpu", "": 0})
    if args.adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, args.adapter)
    model.eval()

    todo = [p for p in pairs if p["id"] not in done]
    print("%s: %d of %d pairs to ask" % (args.name, len(todo), len(pairs)), flush=True)
    with open(resp_path, "a") as fh:
        for i in range(0, len(todo), args.batch):
            chunk = todo[i:i + args.batch]
            texts = [prompting.prompt_text(tok, contexts[p["id"]][0], p["nl"]) for p in chunk]
            enc = tok(texts, return_tensors="pt", padding=True, add_special_tokens=False)
            t0 = time.time()
            with torch.no_grad():
                out = model.generate(**enc, max_new_tokens=args.max_new_tokens, do_sample=False,
                                     pad_token_id=tok.pad_token_id or tok.eos_token_id)
            dt = (time.time() - t0) / len(chunk)
            for p, seq in zip(chunk, out):
                gen = seq[enc["input_ids"].shape[1]:]
                content = tok.decode(gen, skip_special_tokens=True)
                row = {"model": args.name, "id": p["id"], "thinking": "off", "nl": p["nl"], "content": content,
                       "prediction": qualify.extract(content), "latency_s": round(dt, 2),
                       "completion_tokens": int((gen != (tok.pad_token_id or -1)).sum())}
                if contexts[p["id"]][1]:
                    row["context_ids"] = contexts[p["id"]][1]
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                print("%-8s %-40s %s" % (p["id"], row["prediction"][:40], p["css"]), flush=True)
            fh.flush()


if __name__ == "__main__":
    main()
