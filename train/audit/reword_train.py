"""Replace each training pair's human paraphrases with MODEL-written ones.

THE TEST. Rewording eval_t5 costs ~20 points while costing the holdout ~0. The surviving
explanation is that eval_t5's phrasings share an author with the training corpus, so the model
is partly completing familiar wording rather than parsing. If that is right, training on more
DIVERSELY worded requests should narrow the original-vs-reworded gap.

Three explanations for the gap have already been falsified (length/register, synonym rarity,
synonym presence -- see FINDINGS), so this is a hypothesis under test, not a fix being applied.

TOTAL ROWS ARE HELD CONSTANT, deliberately. Each pair keeps its canonical `nl` plus exactly
two paraphrases, as now -- only the paraphrases' SOURCE changes, from the original authoring
process to a model. Same pairs, same row count, same gradient steps, so a delta against
0.8b-t5-e1 (one epoch, same corpus size) isolates phrasing diversity from training volume.
Adding rows instead would have confounded the two, which is the mistake the pseudo-d3 and
arity arms both made in a different form.

Identifiers must survive verbatim or the row teaches a request its answer does not fit; the
guard rejects those and the pair falls back to its original paraphrases.

    python3 train/audit/reword_train.py --out workspace/trainset-t5-rw
"""
import argparse, glob, json, os, re, sys, time

HERE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "tune"))
import prompting

SYS = """You rewrite a developer's code-search request using different words.

Rules:
- Keep the meaning EXACTLY. Definitions stay definitions; call sites stay call sites.
- Change the wording substantially; do not reuse the original's phrasing.
- Copy every identifier (function, class, method, variable name) EXACTLY, character for
  character. Never translate, abbreviate, case-change or pluralise one.
- Reply with the rewritten request only: one line, no quotes, no preamble.
"""

def idents(css):
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
    ap.add_argument("--base", default="/home/teague/.cache/huggingface/hub/models--Qwen--Qwen3.5-4B/snapshots/851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a")
    ap.add_argument("--quant", default="4bit")
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--out", default="workspace/trainset-t5-rw")
    ap.add_argument("--n-para", type=int, default=2)
    a = ap.parse_args()

    srcs = [("workspace/trainset-t5/pairs.jsonl", "trainset")]
    srcs += [(p, "trainpairs") for p in sorted(glob.glob("train/pairs/accepted-*.jsonl"))]
    pairs = []
    for p, kind in srcs:
        for l in open(os.path.join(HERE, p)):
            if l.strip():
                r = json.loads(l); r["_src"] = p; pairs.append(r)
    print("rewording %d pairs x %d paraphrases" % (len(pairs), a.n_para), flush=True)

    import torch
    from transformers import AutoTokenizer
    from train_qlora import load_model
    tok = AutoTokenizer.from_pretrained(a.base); tok.padding_side = "left"
    model, dev = load_model(a.base, False, a.quant, "float16"); model.eval()
    pad = tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id
    stop = sorted({i for i in (tok.convert_tokens_to_ids(prompting.end_of_turn(tok)),
                               tok.eos_token_id) if isinstance(i, int)})
    # one pass per paraphrase slot; slot 2 is seeded from paraphrase 1 so the two differ
    got = {r["id"]: [] for r in pairs}
    t0 = time.time()
    for slot in range(a.n_para):
        todo = [r for r in pairs]
        for i in range(0, len(todo), a.batch):
            chunk = todo[i:i + a.batch]
            prompts = []
            for r in chunk:
                prev = got[r["id"]]
                extra = ("\nDo not reuse this earlier rewrite: %s" % prev[-1]) if prev else ""
                prompts.append(prompting.prompt_text(tok, SYS + extra, r["nl"]))
            enc = tok(prompts, return_tensors="pt", padding=True).to(dev)
            with torch.no_grad():
                gen = model.generate(**enc, max_new_tokens=48, do_sample=True, temperature=0.8,
                                     top_p=0.95, pad_token_id=pad, eos_token_id=stop or pad)
            for r, g in zip(chunk, gen):
                txt = clean(tok.decode(g[enc["input_ids"].shape[1]:], skip_special_tokens=True))
                need = idents(r["css"])
                if (txt and len(txt) <= 200 and all(n in txt for n in need)
                        and txt.lower() != r["nl"].lower() and txt not in got[r["id"]]):
                    got[r["id"]].append(txt)
            if i % (a.batch * 40) == 0:
                done = sum(len(v) for v in got.values())
                print("  slot %d  %d/%d pairs  %d paraphrases  %.0fs"
                      % (slot, i + len(chunk), len(todo), done, time.time() - t0), flush=True)

    outdir = os.path.join(HERE, a.out); os.makedirs(outdir, exist_ok=True)
    kept = fallback = 0
    byfile = {}
    for r in pairs:
        new = got[r["id"]][:a.n_para]
        if len(new) == a.n_para:
            r["paraphrases_original"] = r.get("paraphrases") or []
            r["paraphrases"] = new; r["paraphrase_source"] = "model:" + os.path.basename(a.base)
            kept += 1
        else:
            fallback += 1
        byfile.setdefault(r["_src"], []).append(r)
    for src, rows in byfile.items():
        dst = os.path.join(outdir, os.path.basename(src))
        with open(dst, "w") as fh:
            for r in rows:
                r.pop("_src", None); fh.write(json.dumps(r) + "\n")
        print("wrote %d -> %s" % (len(rows), dst))
    print("\npairs with model paraphrases: %d   fell back to originals: %d" % (kept, fallback))

if __name__ == "__main__":
    main()
