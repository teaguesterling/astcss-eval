"""QLoRA fine-tuning on a tune/build_dataset.py dataset, sized for the 2080 Ti.

usage: ~/.venvs/astcss-tune/bin/python tune/train_qlora.py --base PATH --data workspace/datasets/NAME
           --out workspace/adapters/RUN [--epochs 2] [--lr 1e-4] [--rank 16] [--alpha 32]
           [--accum 16] [--max-len 1024] [--limit N] [--embed-cpu]

Setup proven by tune/smoke_qlora.py and workspace/diag_forward.py (2026-09-14): NF4
4-bit base with double quantization, float16 compute (sm_75 has no bfloat16), LoRA on
all linear layers, gradient checkpointing, no prepare_model_for_kbit_training (it
upcasts the 248k embedding to float32 and runs out of memory).

Embedding placement. On the GPU (default) the loaded model takes ~7.3 GiB and a
20-token forward ~0.14 s. --embed-cpu saves ~1.9 GiB for long prompts but installs
~478 accelerate offload hooks whose host-to-device copies made the same forward ~0.41 s
(80 % of CUDA time was pageable Memcpy HtoD). Use it only when card-length prompts do
not fit.

Each row trains on prompting.prompt_text(system, request) + selector + end-of-turn, with
the loss on the selector and end-of-turn tokens only. Batch size 1 with gradient
accumulation; rows are visited in a seeded shuffle each epoch. The adapter is saved after
every epoch with the validation loss, the dataset manifest and the prompt format version.
Validation loss is a sanity signal only; checkpoints are judged by execution match on the
eval (tune/local_generate.py then qualify.py score).
"""
import argparse
import json
import math
import os
import random
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "tune"))
import prompting  # noqa: E402


def load_rows(path, limit=0):
    rows = [json.loads(l) for l in open(path) if l.strip()]
    return rows[:limit] if limit else rows


def encode(tok, row, max_len):
    msgs = row["messages"]
    system = next((m["content"] for m in msgs if m["role"] == "system"), None)
    request = next(m["content"] for m in msgs if m["role"] == "user")
    answer = next(m["content"] for m in msgs if m["role"] == "assistant")
    prompt_ids = tok(prompting.prompt_text(tok, system, request), add_special_tokens=False).input_ids
    answer_ids = tok(answer + prompting.end_of_turn(tok), add_special_tokens=False).input_ids
    ids = (prompt_ids + answer_ids)[-max_len:]
    n_answer = min(len(answer_ids), len(ids))
    return ids, n_answer


def load_model(base, embed_cpu, quant="4bit"):
    """Base model for training or generation; returns (model, device for input ids).

    quant="4bit": NF4 with double quantization, float16 compute (the 9B).
    quant="none": plain float16 weights, no bitsandbytes -- for small models (Qwen3.5-0.8B
    is ~1.6 GiB in float16), where LoRA on the full-precision base is cheaper and exact.
    """
    import torch
    from transformers import AutoModelForCausalLM, BitsAndBytesConfig
    device_map = {"model.embed_tokens": "cpu", "": 0} if embed_cpu else {"": 0}
    if quant == "none":
        model = AutoModelForCausalLM.from_pretrained(base, dtype=torch.float16, device_map=device_map)
    else:
        bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.float16,
                                 bnb_4bit_use_double_quant=True, llm_int8_enable_fp32_cpu_offload=embed_cpu)
        model = AutoModelForCausalLM.from_pretrained(base, quantization_config=bnb, dtype=torch.float16, device_map=device_map)
    return model, ("cpu" if embed_cpu else "cuda:0")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--alpha", type=int, default=32)
    ap.add_argument("--dropout", type=float, default=0.05)
    ap.add_argument("--accum", type=int, default=16)
    ap.add_argument("--warmup", type=float, default=0.05, help="fraction of optimizer steps")
    ap.add_argument("--max-len", type=int, default=1024)
    ap.add_argument("--limit", type=int, default=0, help="first N training rows (smoke runs)")
    ap.add_argument("--seed", type=int, default=17)
    ap.add_argument("--embed-cpu", action="store_true", help="embedding table on the CPU (long prompts only; ~3x slower)")
    ap.add_argument("--quant", choices=("4bit", "none"), default="4bit",
                    help="4bit (NF4, the 9B) or none (float16 base, small models)")
    args = ap.parse_args()

    import torch
    import torch.nn.functional as F
    from peft import LoraConfig, get_peft_model
    from transformers import AutoTokenizer

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    os.makedirs(args.out, exist_ok=True)
    log = open(os.path.join(args.out, "train.log"), "a")

    def say(msg):
        line = "%s %s" % (time.strftime("%H:%M:%S"), msg)
        print(line, flush=True)
        log.write(line + "\n")
        log.flush()

    tok = AutoTokenizer.from_pretrained(args.base)
    train = [encode(tok, r, args.max_len) for r in load_rows(os.path.join(args.data, "train.jsonl"), args.limit)]
    val = [encode(tok, r, args.max_len) for r in load_rows(os.path.join(args.data, "val.jsonl"))]
    lens = sorted(len(i) for i, _ in train)
    say("train rows %d (median %d tokens, max %d), val rows %d" % (len(train), lens[len(lens) // 2], lens[-1], len(val)))

    model, dev = load_model(args.base, args.embed_cpu, args.quant)
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()
    model = get_peft_model(model, LoraConfig(r=args.rank, lora_alpha=args.alpha, lora_dropout=args.dropout,
                                             target_modules="all-linear", task_type="CAUSAL_LM"))
    trainable = [p for p in model.parameters() if p.requires_grad]
    # LoRA weights train in float32 for stable updates; the frozen base stays 4-bit/float16.
    for p in trainable:
        p.data = p.data.float()
    say("trainable params %d; embedding on %s; allocated %.0f MiB" % (
        sum(p.numel() for p in trainable), "cpu" if args.embed_cpu else "gpu", torch.cuda.memory_allocated() / 2**20))

    opt = torch.optim.AdamW(trainable, lr=args.lr, weight_decay=0.0)
    total_steps = math.ceil(len(train) * args.epochs / args.accum)
    warm = max(1, int(total_steps * args.warmup))
    sched = torch.optim.lr_scheduler.LambdaLR(
        opt, lambda s: (s + 1) / warm if s < warm else 0.5 * (1 + math.cos(math.pi * (s - warm) / max(1, total_steps - warm))))
    # No GradScaler. Loss scaling protects fp16 gradients from underflow, but here the
    # failure was overflow: with a scaler every smoke-run step had NaN gradients even at
    # scale 128 (and all were skipped, so the adapter never changed), while an unscaled
    # backward on the same row is finite in every kernel/autocast mode
    # (workspace/diag_nan_grad.py). The LoRA weights themselves are float32. A step whose
    # gradients are not all finite is skipped and counted instead of applied.
    skipped = 0

    def loss_of(ids, n_answer):
        x = torch.tensor([ids], device=dev)
        out = model(input_ids=x, logits_to_keep=n_answer + 1)
        logits = out.logits[:, :-1].float()
        target = x[:, -n_answer:].to(logits.device)
        return F.cross_entropy(logits.reshape(-1, logits.shape[-1]), target.reshape(-1))

    def val_loss():
        model.eval()
        t = time.time()
        with torch.no_grad():
            total = sum(loss_of(i, n).item() for i, n in val)
        model.train()
        return total / max(1, len(val)), time.time() - t

    vl, vt = val_loss()
    say("val loss before training %.4f (%.1fs for %d rows)" % (vl, vt, len(val)))
    step, t0 = 0, time.time()
    model.train()
    for epoch in range(1, args.epochs + 1):
        order = list(range(len(train)))
        random.Random("%d-%d" % (args.seed, epoch)).shuffle(order)
        running, seen = 0.0, 0
        for k, idx in enumerate(order, 1):
            ids, n = train[idx]
            with torch.autocast("cuda", dtype=torch.float16):
                loss = loss_of(ids, n) / args.accum
            loss.backward()
            running += loss.item() * args.accum
            seen += 1
            if k % args.accum == 0 or k == len(order):
                gnorm = float(torch.nn.utils.clip_grad_norm_(trainable, 1.0))
                if math.isfinite(gnorm):
                    opt.step()
                else:
                    skipped += 1  # a NaN/inf gradient: never apply it
                opt.zero_grad(set_to_none=True)
                sched.step()
                step += 1
                if step % 10 == 0 or step <= 3:
                    el = time.time() - t0
                    say("epoch %d step %d/%d loss %.4f lr %.2e grad %.3g skipped %d  %.2fs/row  eta %.0f min  peak %.0f MiB" % (
                        epoch, step, total_steps, running / seen, sched.get_last_lr()[0], gnorm, skipped,
                        el / (step * args.accum), el / step * (total_steps - step) / 60, torch.cuda.max_memory_allocated() / 2**20))
                    running, seen = 0.0, 0
        vl, vt = val_loss()
        ckpt = os.path.join(args.out, "epoch%d" % epoch)
        model.save_pretrained(ckpt)
        json.dump({"epoch": epoch, "val_loss": vl, "args": vars(args), "prompt_format": prompting.FORMAT_VERSION,
                   "dataset_manifest": json.load(open(os.path.join(args.data, "manifest.json")))},
                  open(os.path.join(ckpt, "run.json"), "w"), indent=2)
        say("epoch %d done: val loss %.4f (%.1fs) -> %s; peak %.0f MiB" % (
            epoch, vl, vt, ckpt, torch.cuda.max_memory_allocated() / 2**20))


if __name__ == "__main__":
    main()
