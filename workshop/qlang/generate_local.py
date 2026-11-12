"""Run a local HF model over the cron eval and write preds.jsonl.

    python3 generate_local.py --base <path> --out preds-base.jsonl [--adapter DIR]

Deliberately the same prompt path a trained model would get: the card in the system
position, the request as the user turn, greedy decoding, thinking off.
"""
import argparse, json, os, sys, time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tune"))
import prompting  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--adapter")
    ap.add_argument("--ref", default=os.path.join(HERE, "data/eval.jsonl"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--batch", type=int, default=12)
    ap.add_argument("--max-new-tokens", type=int, default=96)
    ap.add_argument("--quant", choices=("4bit","none"), default="none")
    ap.add_argument("--dtype", choices=("float16","bfloat16"), default="float16")
    ap.add_argument("--card", help="override the system prompt: a file path, or 'none' for no card at all")
    a = ap.parse_args()

    import torch
    from transformers import AutoTokenizer
    from train_qlora import load_model

    override = None
    if a.card == "none":
        override = False                     # no system message at all
    elif a.card:
        override = open(a.card).read()
    rows = []
    for i, line in enumerate(open(a.ref)):
        ms = json.loads(line)["messages"]
        card = next(m["content"] for m in ms if m["role"] == "system")
        if override is False:
            card = None
        elif override:
            card = override
        rows.append({"id": i, "system": card,
                     "request": next(m["content"] for m in ms if m["role"] == "user")})

    tok = AutoTokenizer.from_pretrained(a.base)
    tok.padding_side = "left"
    model, dev = load_model(a.base, False, a.quant, a.dtype)
    if a.adapter:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, a.adapter)
    model.eval()
    pad = tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id
    stop = sorted({i for i in (tok.convert_tokens_to_ids(prompting.end_of_turn(tok)),
                               tok.eos_token_id) if isinstance(i, int)})
    t0 = time.time()
    with open(a.out, "w") as fh:
        for i in range(0, len(rows), a.batch):
            chunk = rows[i:i + a.batch]
            texts = [prompting.prompt_text(tok, r["system"], r["request"]) for r in chunk]
            enc = tok(texts, return_tensors="pt", padding=True, add_special_tokens=False).to(dev)
            with torch.no_grad():
                out = model.generate(**enc, max_new_tokens=a.max_new_tokens, do_sample=False,
                                     pad_token_id=pad, eos_token_id=stop)
            for r, seq in zip(chunk, out):
                gen = tok.decode(seq[enc["input_ids"].shape[1]:], skip_special_tokens=True)
                fh.write(json.dumps({"id": r["id"], "request": r["request"],
                                     "prediction": gen}) + "\n")
    print("%d rows in %.0fs -> %s" % (len(rows), time.time() - t0, a.out))


if __name__ == "__main__":
    main()
