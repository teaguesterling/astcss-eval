"""Build a supervised NL -> selector dataset from the verified training pairs.

usage: python3 tune/build_dataset.py NAME [--langs python,rust] [--system none|card|per-language]
           [--card card_v1c.md] [--no-paraphrases] [--cap-template N] [--val-frac 0.1] [--seed S]

Writes workspace/datasets/NAME/{train,val}.jsonl as chat rows
({"messages": [system?, user, assistant], "pair_id", "lang", "tier", "fixture"}) and a
manifest.json recording every choice, the card's sha256 and the counts.

Rules it keeps:
- The held-out eval stays held out: pilot.eval_overlap is re-run over every row, and
  any hit aborts the build (the drafting gate already rejected these; this is a guard).
- A pair and its paraphrases are one unit. The train/val split is by pair id, so a
  paraphrase of a validation request never appears in training.
- Train and serve prompts must match. --system card uses the same card the qualifier
  sends (card_v1c.md for Python); --system per-language uses train/cards/card_<lang>.md.
- --cap-template N keeps at most N pairs per (request template, selector shape), so
  "calls to X" (57 pairs) doesn't drown the rarer shapes. Which pairs survive a cap is
  a seeded hash of the pair id, not file order.
"""
import argparse
import collections
import glob
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
import pilot  # noqa: E402


def shape(css):
    return re.sub(r'"[^"]*"', '"S"', re.sub(r"#[\w.]+", "#N", css))


def template(p):
    names = set(re.findall(r"#(\w+)", p["css"])) | {w.strip("_") for w in re.findall(r'"([^"]*)"', p["css"])}
    return " ".join("N" if w.strip(",.?") in names else w for w in p["nl"].split())


def rank(seed, text):
    return hashlib.sha256(("%s:%s" % (seed, text)).encode()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--langs", help="comma-separated (default: all)")
    ap.add_argument("--system", choices=("none", "card", "per-language"), default="none")
    ap.add_argument("--card", default="card_v1c.md", help="system prompt for --system card")
    ap.add_argument("--no-paraphrases", action="store_true")
    ap.add_argument("--cap-template", type=int, default=0)
    ap.add_argument("--val-frac", type=float, default=0.1)
    ap.add_argument("--train-frac", type=float, default=1.0, help="keep this fraction of training pairs (learning curves)")
    ap.add_argument("--seed", default="astcss-train-v1")
    args = ap.parse_args()

    langs = set(args.langs.split(",")) if args.langs else None
    pairs = []
    for path in sorted(glob.glob(os.path.join(HERE, "train/pairs/accepted-*.jsonl"))):
        for line in open(path):
            if line.strip():
                p = json.loads(line)
                p["lang"] = p["id"].split("-")[1]
                if not langs or p["lang"] in langs:
                    pairs.append(p)

    overlap = pilot.eval_overlap(pairs)
    if overlap:
        sys.exit("eval overlap in %d training pairs, refusing to build: %s" % (len(overlap), dict(list(overlap.items())[:3])))

    # Split first, with its own salt, so the validation pairs are the same whatever cap
    # or prompt a variant uses; then cap the training side only. (The first version
    # ranked both with one hash, so the validation pairs were always the ones a cap kept.)
    for p in pairs:
        p["split"] = "val" if int(rank(args.seed + ":split", p["id"])[:8], 16) / 0x100000000 < args.val_frac else "train"
    dropped_by_cap = 0
    if args.cap_template:
        groups = collections.defaultdict(list)
        for p in pairs:
            if p["split"] == "train":
                groups[(template(p), shape(p["css"]))].append(p)
        kept = [p for p in pairs if p["split"] == "val"]
        for members in groups.values():
            members.sort(key=lambda p: rank(args.seed + ":cap", p["id"]))
            kept.extend(members[:args.cap_template])
            dropped_by_cap += max(0, len(members) - args.cap_template)
        pairs = sorted(kept, key=lambda p: p["id"])
    # Learning-curve subsets: a seeded fraction of the CAPPED training pairs, chosen by hash
    # of the pair id (not file order, which is sorted by language). Applied after the cap so
    # the cap never depends on the fraction: subsets nest (25 % of pairs inside 50 % inside
    # the full set) and validation pairs are untouched, the same 85 in every subset.
    dropped_by_frac = 0
    if args.train_frac < 1.0:
        keep = [p for p in pairs if p["split"] == "val"
                or int(rank(args.seed + ":frac", p["id"])[:8], 16) / 0x100000000 < args.train_frac]
        dropped_by_frac = len(pairs) - len(keep)
        pairs = keep

    cards = {}
    if args.system == "card":
        cards = {None: open(os.path.join(HERE, args.card)).read()}
    elif args.system == "per-language":
        for p in pairs:
            if p["lang"] not in cards:
                cards[p["lang"]] = open(os.path.join(HERE, "train/cards/card_%s.md" % p["lang"])).read()

    out_dir = os.path.join(HERE, "workspace", "datasets", args.name)
    os.makedirs(out_dir, exist_ok=True)
    counts = collections.Counter()
    by = collections.defaultdict(collections.Counter)
    with open(os.path.join(out_dir, "train.jsonl"), "w") as tr, open(os.path.join(out_dir, "val.jsonl"), "w") as va:
        for p in pairs:
            split = p["split"]
            requests = [p["nl"]] + ([] if args.no_paraphrases else list(p.get("paraphrases") or []))
            system = cards.get(None) if args.system == "card" else cards.get(p["lang"])
            for req in requests:
                msgs = ([{"role": "system", "content": system}] if system else []) + [
                    {"role": "user", "content": req}, {"role": "assistant", "content": p["css"]}]
                row = {"messages": msgs, "pair_id": p["id"], "lang": p["lang"], "tier": p["tier"], "fixture": p["fixture"]}
                (va if split == "val" else tr).write(json.dumps(row, ensure_ascii=False) + "\n")
                counts[split] += 1
                by[split][p["lang"]] += 1
            counts[split + "_pairs"] += 1

    manifest = {"name": args.name, "args": vars(args), "pairs": len(pairs), "dropped_by_train_frac": dropped_by_frac,
                "dropped_by_template_cap": dropped_by_cap,
                "rows": dict(counts), "rows_by_lang": {k: dict(v) for k, v in by.items()},
                "cards_sha256": {str(k): hashlib.sha256(v.encode()).hexdigest() for k, v in cards.items()},
                "distinct_selector_shapes": len({shape(p["css"]) for p in pairs})}
    with open(os.path.join(out_dir, "manifest.json"), "w") as fh:
        json.dump(manifest, fh, indent=2)
    print(json.dumps({k: manifest[k] for k in ("pairs", "dropped_by_template_cap", "rows", "distinct_selector_shapes")}))


if __name__ == "__main__":
    main()
