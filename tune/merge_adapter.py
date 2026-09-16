"""Merge a LoRA adapter into its base and write a full safetensors model.

    python3 tune/merge_adapter.py --adapter workspace/adapters/lc-nosys-lang-f100/epoch2 \
        --out workspace/merged/qwen3.5-9b-langtag

Why a merge at all: the Tiiny imports whole models, not adapters -- safetensors only, and its
import toolkit matches on the base's own layout (`Qwen3_5ForConditionalGeneration`, vision tower
and preprocessor configs included), so every auxiliary file the base ships has to come along.
The merge is exact: W <- W + (alpha/r) * B*A, folded into the weights, no adapter at serving time.

Two things to know before trusting the result:
  - An adapter trained against an NF4 base (the 4B ladder run) learned its correction against
    QUANTIZED weights; merging into float16 is standard but not identity, so the merged model
    must be re-scored rather than assumed to keep the adapter's number.
  - Merging on the CPU in float16 needs roughly the base's full size in RAM (9B ~ 19 GB).

After it writes, score the merged weights exactly like any other local model:

    tune/local_generate.py --base workspace/merged/<name> --name local:<name> --quant none \
        --card <the card it was trained with> --out runs/<name>
    qualify.py score --out runs/<name>
"""
import argparse
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Files the device toolkit matches on that save_pretrained() will not write for us.
CARRY = ("preprocessor_config.json", "chat_template.json", "chat_template.jinja",
         "video_preprocessor_config.json", "processor_config.json", "generation_config.json")


def load_base(path, dtype):
    """Load the base the SAME WAY TRAINING DID, or the adapter binds to nothing.

    train_qlora.py uses AutoModelForCausalLM, so every adapter key is
    `base_model.model.model.layers.<n>...`. Loading the same checkpoint as
    AutoModelForImageTextToText puts the text stack at `model.language_model.layers.<n>`
    instead, PEFT finds none of those keys, and merge_and_unload() returns the base
    unchanged with only a UserWarning (2026-09-16: all 372 adapter tensors reported
    missing, max|delta| against the base 2.98e-08 — fp16 round-trip noise — including on
    embed_tokens, which the adapter never touched).

    So: CausalLM first, and verify_merge() below proves the deltas landed."""
    import torch
    import transformers
    kinds = [getattr(transformers, n, None) for n in
             ("AutoModelForCausalLM", "AutoModelForImageTextToText", "AutoModel")]
    errors = []
    for cls in filter(None, kinds):
        try:
            m = cls.from_pretrained(path, dtype=getattr(torch, dtype), device_map="cpu",
                                    low_cpu_mem_usage=True)
            print("loaded with %s: %s" % (cls.__name__, type(m).__name__))
            return m
        except Exception as e:                      # wrong head for this checkpoint
            errors.append("%s: %s: %s" % (cls.__name__, type(e).__name__, str(e)[:120]))
    sys.exit("could not load %s\n  " % path + "\n  ".join(errors))


def verify_merge(base, out, adapter):
    """A merge that applied nothing is the failure this script exists to catch, and it is silent.
    Compare the written tensors against the base: modules the adapter targeted must differ by far
    more than fp16 round-trip noise, and a module it never touched must not."""
    import glob
    from safetensors import safe_open
    targets = set(json.load(open(os.path.join(adapter, "adapter_config.json")))["target_modules"])
    src = {}
    for f in sorted(glob.glob(os.path.join(base, "*.safetensors"))):
        with safe_open(f, framework="pt") as h:
            for k in h.keys():
                src[k] = f
    written = sorted(glob.glob(os.path.join(out, "*.safetensors")))
    touched, untouched, missing = [], [], 0
    for f in written:
        with safe_open(f, framework="pt") as hm:
            for k in hm.keys():
                if k not in src:
                    continue
                with safe_open(src[k], framework="pt") as hb:
                    d = (hb.get_tensor(k).float() - hm.get_tensor(k).float()).abs().max().item()
                (touched if any(".%s." % t in k for t in targets) else untouched).append((k, d))
    missing = len(set(src) - {k for f in written for k in safe_open(f, framework="pt").keys()})
    t_max = max((d for _, d in touched), default=0.0)
    u_max = max((d for _, d in untouched), default=0.0)
    print("verify: %d targeted tensors, max|delta| %.6g; %d untouched, max|delta| %.6g; %d base tensors not written"
          % (len(touched), t_max, len(untouched), u_max, missing))
    if t_max <= max(u_max, 1e-6):
        sys.exit("MERGE DID NOT APPLY: targeted weights are indistinguishable from the base. "
                 "Check that the adapter's key prefix matches how the base was loaded.")
    return t_max, u_max, missing


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--adapter", required=True, help="adapter directory (adapter_config.json inside)")
    ap.add_argument("--base", help="override the base recorded in the adapter's config")
    ap.add_argument("--out", required=True)
    ap.add_argument("--dtype", default="float16", choices=("float16", "bfloat16", "float32"))
    ap.add_argument("--shard", default="4GB")
    args = ap.parse_args(argv)

    adapter = args.adapter if os.path.isabs(args.adapter) else os.path.join(HERE, args.adapter)
    out = args.out if os.path.isabs(args.out) else os.path.join(HERE, args.out)
    cfg = json.load(open(os.path.join(adapter, "adapter_config.json")))
    base = args.base or cfg["base_model_name_or_path"]
    if not os.path.exists(base):
        sys.exit("base not found: %s (pass --base)" % base)
    print("adapter %s\n  r=%s alpha=%s targets=%d\nbase %s\nout %s"
          % (adapter, cfg.get("r"), cfg.get("lora_alpha"), len(cfg.get("target_modules") or []), base, out))

    from peft import PeftModel
    from transformers import AutoTokenizer
    t0 = time.time()
    model = load_base(base, args.dtype)
    model = PeftModel.from_pretrained(model, adapter)
    model = model.merge_and_unload()
    print("merged in %.0fs" % (time.time() - t0))

    os.makedirs(out, exist_ok=True)
    model.save_pretrained(out, safe_serialization=True, max_shard_size=args.shard)
    AutoTokenizer.from_pretrained(base).save_pretrained(out)
    carried = []
    for name in CARRY:
        src = os.path.join(base, name)
        if os.path.exists(src) and not os.path.exists(os.path.join(out, name)):
            shutil.copy2(src, os.path.join(out, name))
            carried.append(name)
    total = sum(os.path.getsize(os.path.join(out, f)) for f in os.listdir(out))
    print("wrote %d files, %.1f GB%s" % (len(os.listdir(out)), total / 1e9,
                                         ("; carried " + ", ".join(carried)) if carried else ""))
    print("architectures:", json.load(open(os.path.join(out, "config.json"))).get("architectures"))
    verify_merge(base, out, adapter)
    print("\nre-score it before shipping -- an NF4-trained adapter merged into float16 is not identity:")
    print("  tune/local_generate.py --base %s --name local:merged --quant none --card <card> --out runs/<name>"
          % os.path.relpath(out, HERE))
    return 0


if __name__ == "__main__":
    sys.exit(main())
