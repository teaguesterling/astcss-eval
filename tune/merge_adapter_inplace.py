"""Fold a LoRA adapter into a copy of the base checkpoint, changing nothing else.

    python3 tune/merge_adapter_inplace.py --adapter workspace/adapters/t5-9b-mixed/epoch1 \
        --out workspace/merged/qwen3.5-9b-astcss

Why this exists alongside merge_adapter.py: that script goes through
`AutoModelForCausalLM.from_pretrained` + `save_pretrained`, which is the only way to get PEFT to
bind the adapter -- and which REWRITES the model. On Qwen3.5 the base ships as
`Qwen3_5ForConditionalGeneration` (`model_type: qwen3_5`, nested text_config/vision_config, a
27-block vision tower). Round-tripping it through the CausalLM head produces
`Qwen3_5ForCausalLM` / `qwen3_5_text` and silently drops every `model.visual.*` tensor -- 312 of
them on the 4B. That is fine for local scoring and fine on Hugging Face. It is NOT fine for the
Tiiny, whose import toolkit matches on the base's own layout.

So this script never constructs a model. It copies the base's safetensors shards tensor by tensor,
adds `(alpha/r) * B @ A` to the 248 tensors the adapter targeted, and copies every other file
byte for byte. The output's config.json, index, shard names, dtype, vision tower and tokenizer are
the base's, unchanged.

Key mapping is the one thing that can silently go wrong, so it is asserted rather than assumed.
train_qlora.py loaded the base as CausalLM, so the adapter's keys are

    base_model.model.model.layers.<n>.<module>.lora_{A,B}.weight

while the checkpoint on disk calls the same weight

    model.language_model.layers.<n>.<module>.weight

Every adapter pair must resolve to a real base tensor of the right shape or the script exits.

Caveat unchanged from the other path: an adapter fitted against NF4 weights and folded into bf16
is not identity. Re-score the output before shipping it.
"""
import argparse
import glob
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def adapter_deltas(adapter):
    """-> {base_key: (A, B, scale)}, keyed by the name the CHECKPOINT uses."""
    from safetensors.torch import load_file
    cfg = json.load(open(os.path.join(adapter, "adapter_config.json")))
    if cfg.get("peft_type") != "LORA":
        sys.exit("not a LoRA adapter: peft_type=%r" % cfg.get("peft_type"))
    if cfg.get("modules_to_save"):
        sys.exit("modules_to_save=%r -- this script folds lora_A/B only" % cfg["modules_to_save"])
    r, alpha = cfg["r"], cfg["lora_alpha"]
    # rsLoRA scales by alpha/sqrt(r) instead of alpha/r; getting this wrong is a silent
    # magnitude error, not a crash, so branch on it explicitly.
    scale = alpha / (r ** 0.5) if cfg.get("use_rslora") else alpha / r
    t = load_file(os.path.join(adapter, "adapter_model.safetensors"))
    pairs = {}
    for k, v in t.items():
        if ".lora_A.weight" in k:
            pairs.setdefault(k.replace(".lora_A.weight", ""), {})["A"] = v
        elif ".lora_B.weight" in k:
            pairs.setdefault(k.replace(".lora_B.weight", ""), {})["B"] = v
        else:
            sys.exit("unexpected adapter tensor %r" % k)
    out = {}
    for stem, ab in pairs.items():
        if "A" not in ab or "B" not in ab:
            sys.exit("half a LoRA pair at %r" % stem)
        # base_model.model.model.layers.N.X -> model.language_model.layers.N.X.weight
        core = stem
        for prefix in ("base_model.model.",):
            if core.startswith(prefix):
                core = core[len(prefix):]
        if not core.startswith("model.layers."):
            sys.exit("unrecognised adapter key stem %r" % stem)
        out["model.language_model." + core[len("model."):] + ".weight"] = (ab["A"], ab["B"], scale)
    print("adapter: %d LoRA pairs, r=%s alpha=%s scale=%.4g%s"
          % (len(out), r, alpha, scale, " (rslora)" if cfg.get("use_rslora") else ""))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True)
    ap.add_argument("--base", help="override the base recorded in the adapter's config")
    ap.add_argument("--out", required=True)
    ap.add_argument("--dry-run", action="store_true", help="check the key mapping and stop")
    args = ap.parse_args(argv)

    import torch
    from safetensors import safe_open
    from safetensors.torch import save_file

    adapter = args.adapter if os.path.isabs(args.adapter) else os.path.join(HERE, args.adapter)
    out = args.out if os.path.isabs(args.out) else os.path.join(HERE, args.out)
    base = args.base or json.load(open(os.path.join(adapter, "adapter_config.json")))["base_model_name_or_path"]
    if not os.path.isdir(base):
        sys.exit("base not found: %s (pass --base)" % base)
    deltas = adapter_deltas(adapter)

    shards = sorted(glob.glob(os.path.join(base, "*.safetensors")))
    if not shards:
        sys.exit("no safetensors shards in %s" % base)
    index = {}
    for f in shards:
        with safe_open(f, framework="pt") as h:
            for k in h.keys():
                index[k] = (f, h.get_slice(k).get_shape())
    missing = [k for k in deltas if k not in index]
    if missing:
        sys.exit("%d adapter targets have no base tensor, e.g. %s" % (len(missing), missing[:3]))
    for k, (A, B, _) in deltas.items():
        want = [B.shape[0], A.shape[1]]
        if list(index[k][1]) != want:
            sys.exit("shape mismatch at %s: base %s, B@A %s" % (k, index[k][1], want))
    print("base: %d tensors in %d shards; %d match the adapter, %d untouched"
          % (len(index), len(shards), len(deltas), len(index) - len(deltas)))
    if args.dry_run:
        print("dry run: key mapping and shapes check out; nothing written")
        return 0

    os.makedirs(out, exist_ok=True)
    t0, applied, worst_t, worst_u = time.time(), 0, 0.0, 0.0
    for f in shards:
        tensors = {}
        with safe_open(f, framework="pt") as h:
            for k in h.keys():
                w = h.get_tensor(k)
                if k in deltas:
                    A, B, scale = deltas[k]
                    d = (B.float() @ A.float()) * scale
                    worst_t = max(worst_t, d.abs().max().item())
                    tensors[k] = (w.float() + d).to(w.dtype)
                    applied += 1
                else:
                    tensors[k] = w
        dst = os.path.join(out, os.path.basename(f))
        save_file(tensors, dst, metadata={"format": "pt"})
        del tensors
        print("  %s: wrote %.1f GB" % (os.path.basename(f), os.path.getsize(dst) / 1e9))
    if applied != len(deltas):
        sys.exit("applied %d of %d deltas" % (applied, len(deltas)))

    carried = []
    for name in sorted(os.listdir(base)):
        if name.endswith(".safetensors"):
            continue
        src = os.path.join(base, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(out, name))
            carried.append(name)
    cfg = json.load(open(os.path.join(out, "config.json")))
    total = sum(os.path.getsize(os.path.join(out, f)) for f in os.listdir(out))
    print("merged %d tensors in %.0fs, max|delta| %.6g; wrote %.1f GB; carried %d files: %s"
          % (applied, time.time() - t0, worst_t, total / 1e9, len(carried), ", ".join(carried)))
    print("architectures: %s  model_type: %s" % (cfg.get("architectures"), cfg.get("model_type")))
    print("\nre-score before shipping -- NF4-fitted, bf16-merged is not identity:")
    print("  tune/local_generate.py --base %s --name local:merged --quant 4bit --card <card> --out runs/<name>"
          % os.path.relpath(out, HERE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
