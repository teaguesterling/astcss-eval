"""Have a LOCAL model reword every eval question: same meaning, different words.

WHY. eval_pd2 showed that re-wording is the only test that separates learning from recall --
arm B held a +28 point gap there, which a memorised template would have lost. But eval_pd2 was
43 pairs re-worded BY ME, which does not scale and carries my phrasing habits. Having a model
reword every question gives a robustness reading across the whole suite, and the wording comes
from somewhere other than the author of the originals.

THE INVARIANT THAT MATTERS. A question like "where is run_user defined" is answerable only
because `run_user` appears in it. If a reword drops or alters an identifier, the pair becomes
unanswerable and EVERY model loses the point equally -- which looks like a robustness failure
but is really a broken question. So identifiers are extracted from the reference selector and
checked for verbatim survival; a reword that loses one is rejected, not shipped.

The rewording model is the BASE model with no adapter: the fine-tuned adapters answer with
selectors, which is the wrong job here.

    python3 holdout/reword.py --pairs-dir holdout --out holdout_rw
"""
import argparse, json, os, re, sys, time

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tune"))
import qualify, prompting

SYS = """You rewrite a developer's code-search request using different words.

Rules:
- Keep the meaning EXACTLY. If the original asks for definitions, the rewrite asks for
  definitions; if it asks for call sites, the rewrite asks for call sites.
- Change the wording substantially. Do not reuse the original's phrasing.
- Copy every identifier (function, class, method, variable name) EXACTLY as written,
  character for character. Never translate, abbreviate, case-change or pluralise one.
- Reply with the rewritten request only: one line, no quotes, no explanation, no preamble.
"""

def idents(css):
    """Identifiers the question must keep: names after # and inside attribute values."""
    out = set(re.findall(r'#([A-Za-z_][\w$?!]*)', css))
    out |= set(re.findall(r'=\s*"([^"]+)"', css))
    out |= set(re.findall(r':(?:calls|called-by)\(([A-Za-z_][\w$?!]*)\)', css))
    return out

def clean(t):
    t = (t or "").strip().split("\n")[0].strip()
    t = re.sub(r'^(rewritten request|rewrite|answer)\s*:\s*', '', t, flags=re.I)
    return t.strip().strip('"').strip()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs-dir", required=True)
    ap.add_argument("--out", required=True, help="new pairs dir name")
    ap.add_argument("--base", default="/home/teague/.cache/huggingface/hub/models--Qwen--Qwen3.5-9B/snapshots/c202236235762e1c871ad0ccb60c8ee5ba337b9a")
    ap.add_argument("--quant", default="4bit")
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--max-new-tokens", type=int, default=64)
    a = ap.parse_args()

    import torch
    from transformers import AutoTokenizer
    from train_qlora import load_model
    qualify.PAIRS_DIR = a.pairs_dir
    pairs = qualify.load_pairs()
    print("rewording %d pairs from %s" % (len(pairs), a.pairs_dir), flush=True)

    tok = AutoTokenizer.from_pretrained(a.base); tok.padding_side = "left"
    model, dev = load_model(a.base, False, a.quant, "float16"); model.eval()
    pad = tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id
    stop = sorted({i for i in (tok.convert_tokens_to_ids(prompting.end_of_turn(tok)),
                               tok.eos_token_id) if isinstance(i, int)})
    out, kept, rej = [], 0, {"lost-identifier": 0, "empty": 0, "unchanged": 0, "too-long": 0}
    t0 = time.time()
    for i in range(0, len(pairs), a.batch):
        chunk = pairs[i:i + a.batch]
        texts = [prompting.prompt_text(tok, SYS, p["nl"]) for p in chunk]
        enc = tok(texts, return_tensors="pt", padding=True).to(dev)
        with torch.no_grad():
            gen = model.generate(**enc, max_new_tokens=a.max_new_tokens, do_sample=False,
                                 pad_token_id=pad, eos_token_id=stop or pad)
        for p, g in zip(chunk, gen):
            txt = clean(tok.decode(g[enc["input_ids"].shape[1]:], skip_special_tokens=True))
            need = idents(p["css"])
            if not txt:
                rej["empty"] += 1; continue
            if len(txt) > 220:
                rej["too-long"] += 1; continue
            if " ".join(txt.lower().split()) == " ".join(p["nl"].lower().split()):
                rej["unchanged"] += 1; continue
            missing = [n for n in need if n not in txt]
            if missing:
                rej["lost-identifier"] += 1; continue
            q = dict(p); q["nl"] = txt; q["paraphrases"] = []; q["reworded_from"] = p["nl"]
            q["reword_model"] = os.path.basename(a.base)
            out.append(q); kept += 1
        if i % 40 == 0:
            print("  %d/%d kept=%d %.0fs" % (i + len(chunk), len(pairs), kept, time.time() - t0), flush=True)
    d = os.path.join(HERE, a.out, "pairs")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "accepted-rw.jsonl"), "w") as fh:
        for r in out: fh.write(json.dumps(r) + "\n")
    print("\nkept %d of %d -> %s/pairs/accepted-rw.jsonl" % (kept, len(pairs), a.out))
    print("rejected: %s" % {k: v for k, v in rej.items() if v})

if __name__ == "__main__":
    main()
