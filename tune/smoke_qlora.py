"""QLoRA feasibility smoke test on the 2080 Ti: 4-bit load, LoRA, forward+backward.

usage: ~/.venvs/astcss-tune/bin/python tune/smoke_qlora.py MODEL_PATH [SEQ_LEN]
env:   SMOKE_KEEP=32        loss on the last N tokens only (completion-only training)
       SMOKE_EMBED_CPU=1    keep the input embedding table on the CPU

Answers "can this base train on this card", nothing more: which model class loaded,
where the memory goes, peak CUDA memory, step time. The 2080 Ti is sm_75: no native
bfloat16, so compute runs in float16.

First attempt (Qwen3.5-9B, 2026-09-14): the 4-bit load fit at 7.3 GiB, then
prepare_model_for_kbit_training upcast the unquantized 248k-vocab embedding to float32
(3.8 GiB) and ran out of memory before any training. Qwen3.5-9B's lm_head is untied,
so embedding and lm_head are ~1.9 GiB each even in float16.
"""
import os
import sys
import time

import torch
import torch.nn.functional as F
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

path = sys.argv[1]
seq = int(sys.argv[2]) if len(sys.argv) > 2 else 512
KEEP = int(os.environ.get("SMOKE_KEEP", "32"))
# torch 2.14 routes some eager ops (bmm_outer_product, used by the rotary embedding)
# to Triton kernels, and Triton builds a C shim needing Python.h, which this machine
# lacks (no python3.12-dev). Falling back to the eager ops avoids it.
NATIVE_OFF = os.environ.get("SMOKE_DISABLE_NATIVE_DSL", "triton")
if NATIVE_OFF:
    from torch._native import registry as _native
    print("disabling torch native %s overrides: %s" % (NATIVE_OFF, _native.get_dsl_operations(NATIVE_OFF)), flush=True)
    _native.deregister_op_overrides(disable_dsl_names=NATIVE_OFF)
EMBED_CPU = os.environ.get("SMOKE_EMBED_CPU", "1") == "1"
print("torch", torch.__version__, torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0), flush=True)
print("free/total MiB before load:", [x // 2**20 for x in torch.cuda.mem_get_info()], flush=True)
print("seq %d, loss on last %d tokens, embedding on %s" % (seq, KEEP, "cpu" if EMBED_CPU else "gpu"), flush=True)

bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4",
                         bnb_4bit_compute_dtype=torch.float16, bnb_4bit_use_double_quant=True,
                         # bnb refuses any CPU placement without this, even for the one
                         # module (the embedding) that is never quantized anyway.
                         llm_int8_enable_fp32_cpu_offload=EMBED_CPU)
device_map = {"model.embed_tokens": "cpu", "": 0} if EMBED_CPU else {"": 0}
t0 = time.time()
tok = AutoTokenizer.from_pretrained(path)
model = AutoModelForCausalLM.from_pretrained(path, quantization_config=bnb, dtype=torch.float16,
                                             device_map=device_map, low_cpu_mem_usage=True)
print("loaded %s in %.0fs; allocated %.0f MiB" % (type(model).__name__, time.time() - t0,
                                                  torch.cuda.memory_allocated() / 2**20), flush=True)
by_dtype = {}
for name, p in model.named_parameters():
    key = "%s %s" % (p.dtype, p.device)
    by_dtype[key] = by_dtype.get(key, 0) + p.numel() * p.element_size()
print("parameter MiB by dtype/device:", {k: v // 2**20 for k, v in by_dtype.items()}, flush=True)

# Not prepare_model_for_kbit_training: it upcasts every unquantized tensor to float32.
model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
model.enable_input_require_grads()
lora = LoraConfig(r=16, lora_alpha=32, lora_dropout=0.05, task_type="CAUSAL_LM",
                  target_modules="all-linear")
model = get_peft_model(model, lora)
model.print_trainable_parameters()
print("allocated after LoRA %.0f MiB" % (torch.cuda.memory_allocated() / 2**20), flush=True)

ids = tok("You translate code-search requests into astcss selectors. " * 200, return_tensors="pt",
          truncation=True, max_length=seq).input_ids
ids = ids.to("cpu" if EMBED_CPU else 0)
print("seq len", ids.shape[1], flush=True)
opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=1e-4)
torch.cuda.reset_peak_memory_stats()
model.train()
for step in range(3):
    t1 = time.time()
    out = model(input_ids=ids, logits_to_keep=KEEP + 1)
    logits = out.logits[:, :-1].float()
    target = ids[:, -KEEP:].to(logits.device)
    loss = F.cross_entropy(logits.reshape(-1, logits.shape[-1]), target.reshape(-1))
    loss.backward()
    opt.step()
    opt.zero_grad(set_to_none=True)
    torch.cuda.synchronize()
    print("step %d loss %.3f in %.1fs; peak %.0f MiB" % (step, loss.item(), time.time() - t1,
                                                        torch.cuda.max_memory_allocated() / 2**20), flush=True)
print("OK")
