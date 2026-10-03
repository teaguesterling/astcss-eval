#!/usr/bin/env python3
"""Builds Multi-Turn Reflexive Execution-Feedback Dataset for Fine-Tuning.

This compiler takes real model mistakes (from benchmark runs in runs/*) and
synthesized negative errors (syntax errors, 0-match specificity, dialect mismatch),
diagnoses them with DuckDB / Sitting Duck AST introspection, and produces
2-turn Qwen ChatML training examples (Turn 1 Request -> Flawed Shot 1 -> Error Feedback -> Corrected Selector).
"""
import argparse
import glob
import json
import os
import random
import re
import sys
from typing import Any, Dict, List, Set, Tuple

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tune"))

import verify as V
import qualify
from reflexive_repair import ExecutionFeedbackEngine, ReflexivePromptFormatter


def harvest_real_misses(runs_dir: str = "runs") -> List[Dict[str, Any]]:
    """Scan all benchmark runs for actual model mistakes and their references."""
    pairs_by_id = {p["id"]: p for p in qualify.load_pairs()}
    misses = []
    seen = set()

    for score_path in glob.glob(os.path.join(HERE, runs_dir, "*/scores.jsonl")):
        try:
            with open(score_path) as f:
                for line in f:
                    if not line.strip():
                        continue
                    d = json.loads(line)
                    if not d.get("exec_match", False) and d.get("prediction"):
                        pid = d.get("id")
                        pair = pairs_by_id.get(pid)
                        if not pair:
                            continue
                        pred = d.get("prediction")
                        key = (pid, pred)
                        if key in seen:
                            continue
                        seen.add(key)
                        misses.append({
                            "id": pid,
                            "nl": d.get("nl", pair.get("nl")),
                            "shot1": pred,
                            "gold": pair.get("css"),
                            "fixture": pair.get("fixture", "py-variety"),
                            "source": "model_mistake",
                            "run": os.path.basename(os.path.dirname(score_path))
                        })
        except Exception as e:
            print(f"Warning reading {score_path}: {e}")

    return misses


def synthesize_perturbations(pairs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Synthesize realistic negative Shot 1 errors for gold pairs."""
    perturbations = []
    
    for p in pairs:
        gold = p.get("css")
        nl = p.get("nl")
        fx = p.get("fixture", "py-variety")
        pid = p.get("id")
        
        # Perturbation 1: Exact Name Over-specificity (e.g. [name^="update_"] -> #update)
        prefix_match = re.search(r'\[name\^?=["\']([A-Za-z0-9_]+?)_?["\']\]', gold)
        if prefix_match:
            stem = prefix_match.group(1)
            bad_sel = re.sub(r'\[name\^?=["\'][A-Za-z0-9_]+["\']\]', f"#{stem}", gold)
            if bad_sel != gold:
                perturbations.append({
                    "id": pid, "nl": nl, "shot1": bad_sel, "gold": gold, "fixture": fx,
                    "source": "synthetic_exact_name"
                })

        # Perturbation 2: Tree-sitter Raw Node Type instead of Semantic Shorthand
        if ".fn" in gold:
            bad_sel = gold.replace(".fn", "function_definition")
            perturbations.append({
                "id": pid, "nl": nl, "shot1": bad_sel, "gold": gold, "fixture": fx,
                "source": "synthetic_raw_node"
            })
        if ".class" in gold:
            bad_sel = gold.replace(".class", "class_definition")
            perturbations.append({
                "id": pid, "nl": nl, "shot1": bad_sel, "gold": gold, "fixture": fx,
                "source": "synthetic_raw_node"
            })
        if ".finally" in gold:
            bad_sel = gold.replace(".finally", "finally_statement")
            perturbations.append({
                "id": pid, "nl": nl, "shot1": bad_sel, "gold": gold, "fixture": fx,
                "source": "synthetic_raw_node"
            })
        if ".if" in gold:
            bad_sel = gold.replace(".if", "if_statement")
            perturbations.append({
                "id": pid, "nl": nl, "shot1": bad_sel, "gold": gold, "fixture": fx,
                "source": "synthetic_raw_node"
            })

        # Perturbation 3: Cross-language Method Inversion (e.g. .call#append -> .call#push)
        if ".call#append" in gold:
            bad_sel = gold.replace(".call#append", ".call#push")
            perturbations.append({
                "id": pid, "nl": nl, "shot1": bad_sel, "gold": gold, "fixture": fx,
                "source": "synthetic_lang_transfer"
            })
        if ".fn#__init__" in gold:
            bad_sel = gold.replace(".fn#__init__", ".fn#__constructor")
            perturbations.append({
                "id": pid, "nl": nl, "shot1": bad_sel, "gold": gold, "fixture": fx,
                "source": "synthetic_lang_transfer"
            })

        # Perturbation 4: Graph Direction Inversion (::callees <-> ::callers)
        if "::callees" in gold:
            bad_sel = gold.replace("::callees", "::callers")
            perturbations.append({
                "id": pid, "nl": nl, "shot1": bad_sel, "gold": gold, "fixture": fx,
                "source": "synthetic_relation_inversion"
            })
        elif "::callers" in gold:
            bad_sel = gold.replace("::callers", "::callees")
            perturbations.append({
                "id": pid, "nl": nl, "shot1": bad_sel, "gold": gold, "fixture": fx,
                "source": "synthetic_relation_inversion"
            })

        # Perturbation 5: Unsupported Pseudo-class (e.g. :decorated, :typed)
        if "[annotation" in gold:
            bad_sel = re.sub(r'\[annotation[^\]]*\]', ":decorated", gold)
            if bad_sel != gold:
                perturbations.append({
                    "id": pid, "nl": nl, "shot1": bad_sel, "gold": gold, "fixture": fx,
                    "source": "synthetic_bad_pseudo"
                })
        if "[signature" in gold:
            bad_sel = re.sub(r'\[signature[^\]]*\]', ":typed", gold)
            if bad_sel != gold:
                perturbations.append({
                    "id": pid, "nl": nl, "shot1": bad_sel, "gold": gold, "fixture": fx,
                    "source": "synthetic_bad_pseudo"
                })

        # Perturbation 6: Syntax Parse Error (unclosed bracket or bad combinator)
        if "[" in gold and "]" in gold:
            bad_sel = gold.replace("]", "")
            perturbations.append({
                "id": pid, "nl": nl, "shot1": bad_sel, "gold": gold, "fixture": fx,
                "source": "synthetic_syntax_error"
            })

    return perturbations


def build_dataset(
    out_dir: str = "workspace/datasets/reflexive-repairs",
    card_file: str = "card_v1c.md",
    val_ratio: float = 0.1,
    seed: int = 42
):
    """Compile full reflexive multi-turn dataset with diagnosis feedback."""
    os.makedirs(out_dir, exist_ok=True)
    engine = ExecutionFeedbackEngine()
    card_text = open(os.path.join(HERE, card_file)).read() if card_file != "none" and os.path.exists(os.path.join(HERE, card_file)) else ""

    # Collect pairs
    all_pairs = qualify.load_pairs()
    print(f"Loaded {len(all_pairs)} baseline pairs.")

    # 1. Real misses from runs
    real_misses = harvest_real_misses()
    print(f"Harvested {len(real_misses)} real model mistakes from runs/.")

    # 2. Synthetic perturbations
    synthetic_misses = synthesize_perturbations(all_pairs)
    print(f"Generated {len(synthetic_misses)} synthetic perturbation examples.")

    combined = real_misses + synthetic_misses
    random.Random(seed).shuffle(combined)
    print(f"Total candidate reflexive rows: {len(combined)}")

    # Batch evaluate all Shot 1 queries in DuckDB
    print("Batch evaluating all Shot 1 queries in DuckDB...")
    queries = [(f"q_{i}", item.get("fixture", "py-variety"), item["shot1"]) for i, item in enumerate(combined)]
    eval_results = engine.evaluate_batch(queries)

    rows = []
    print("Synthesizing diagnostics and building multi-turn conversations...")
    for idx, item in enumerate(combined):
        qid = f"q_{idx}"
        fx = item.get("fixture", "py-variety")
        nl = item["nl"]
        shot1 = item["shot1"]
        gold = item["gold"]

        exec_res = eval_results.get(qid, {"status": "execution_error", "match_count": 0, "nodes": []})
        feedback = engine.build_feedback(nl, shot1, exec_res, fixture=fx, lang="python")

        # Multi-turn messages format
        messages = [
            {"role": "system", "content": card_text} if card_text else None,
            {"role": "user", "content": nl},
            {"role": "assistant", "content": shot1},
            {"role": "user", "content": feedback},
            {"role": "assistant", "content": gold}
        ]
        messages = [m for m in messages if m is not None]

        rows.append({
            "id": f"{item['id']}_reflexive_{idx}",
            "source": item.get("source", "reflexive"),
            "messages": messages,
            "nl": nl,
            "shot1": shot1,
            "shot1_status": exec_res.get("status"),
            "feedback": feedback,
            "gold": gold
        })

    # Split into train and val
    val_count = max(10, int(len(rows) * val_ratio))
    val_rows = rows[:val_count]
    train_rows = rows[val_count:]

    train_path = os.path.join(out_dir, "train.jsonl")
    val_path = os.path.join(out_dir, "val.jsonl")

    with open(train_path, "w") as f:
        for r in train_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    with open(val_path, "w") as f:
        for r in val_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    print(f"\n=======================================================")
    print(f"Reflexive Dataset Compilation Complete:")
    print(f"  Train: {len(train_rows)} rows -> {train_path}")
    print(f"  Val:   {len(val_rows)} rows -> {val_path}")
    print(f"=======================================================\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="workspace/datasets/reflexive-repairs")
    ap.add_argument("--card", default="card_v1c.md")
    ap.add_argument("--val-ratio", type=float, default=0.1)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    build_dataset(out_dir=args.out, card_file=args.card, val_ratio=args.val_ratio, seed=args.seed)
