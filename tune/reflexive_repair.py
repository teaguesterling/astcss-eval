#!/usr/bin/env python3
"""Reflexive Execution-Feedback Prompting & Repair System for AST Specialists.

When Shot 1 produces an AST error, empty result set (0 matches), or over-match,
this module evaluates the query through Sitting Duck / DuckDB, performs AST
introspection to diagnose the mistake, and constructs a structured environment
or user feedback prompt for a Shot 2 correction.
"""
import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "tune"))

import verify as V
import qualify
import prompting


class ExecutionFeedbackEngine:
    """Evaluates ASTCSS queries in DuckDB and synthesizes diagnostic feedback."""

    def __init__(self, fixtures_dir: str = HERE):
        self.fixtures_dir = fixtures_dir
        self.engine_info = V.engine_identity()

    def evaluate_batch(self, queries: List[Tuple[str, str, str]]) -> Dict[str, Dict[str, Any]]:
        """Batch evaluate [(qid, fixture, selector), ...] in DuckDB."""
        if not queries:
            return {}
        got = V.execute(queries)
        out = {}
        for qid, fx, sel in queries:
            res = got.get(qid, {"error": "no output for query"})
            if "error" in res:
                err_msg = res["error"]
                if "malformed selector" in err_msg or "syntax error" in err_msg.lower() or "parse" in err_msg.lower():
                    status = "parse_error"
                elif "unknown pseudo-class" in err_msg:
                    status = "unknown_pseudo"
                else:
                    status = "execution_error"
                out[qid] = {
                    "status": status,
                    "selector": sel,
                    "match_count": 0,
                    "nodes": [],
                    "error_message": self._clean_error_message(err_msg),
                }
            else:
                nodes = res.get("nodes", [])
                out[qid] = {
                    "status": "success" if len(nodes) > 0 else "empty_match",
                    "selector": sel,
                    "match_count": len(nodes),
                    "nodes": nodes,
                    "error_message": None,
                }
        return out

    def evaluate_selector_on_fixture(self, fixture: str, selector: str) -> Dict[str, Any]:
        """Execute selector against a named fixture using verify.execute."""
        qid = "eval_" + hashlib.sha256(f"{fixture}:{selector}".encode()).hexdigest()[:12]
        res = self.evaluate_batch([(qid, fixture, selector)])
        return res[qid]

    def _clean_error_message(self, raw_err: str) -> str:
        """Strip internal engine prefixes and keep concise error explanation."""
        msg = re.sub(r"^Invalid Input Error:\s*", "", raw_err)
        msg = re.sub(r"For dynamic custom predicates:.*", "", msg, flags=re.S)
        return msg.strip()

    def introspect_fixture_names(self, fixture: str, prefix_or_sub: str, limit: int = 6) -> List[str]:
        """Find matching function/method/class identifiers in the fixture AST."""
        tbl = V._table(fixture)
        pattern = os.path.join(self.fixtures_dir, V.FIXTURES.get(fixture, f"fixtures/{fixture}/*.*"))
        if not glob.glob(pattern, recursive=True):
            return []

        clean_token = re.sub(r"[^A-Za-z0-9_]", "", prefix_or_sub)
        if not clean_token:
            return []

        script = [
            f"CREATE TABLE IF NOT EXISTS {tbl} AS SELECT * FROM read_ast('{V._q(pattern)}');",
            f"SELECT DISTINCT name FROM {tbl} WHERE name IS NOT NULL AND name != '' AND (name LIKE '%{clean_token}%' OR name LIKE '{clean_token}%') LIMIT {limit};"
        ]
        out = V._run_script(script)
        names = [line.strip() for line in out if line.strip() and not line.startswith("Error:") and not line.startswith("@@")]
        return names[:limit]

    def diagnose_empty_match(self, nl_intent: str, selector: str, fixture: Optional[str] = None, lang: str = "python") -> List[str]:
        """Produce specific actionable hints for why selector returned 0 matches."""
        hints = []
        nl_lower = nl_intent.lower()

        # 1. Identifier / Name mismatch
        id_match = re.search(r"#([A-Za-z0-9_]+)", selector)
        name_attr = re.search(r'\[name\s*=\s*["\']([^"\']+)["\']\]', selector)
        target_name = (id_match.group(1) if id_match else (name_attr.group(1) if name_attr else None))

        if target_name and fixture:
            similar = self.introspect_fixture_names(fixture, target_name)
            if not similar:
                # Try prefix/stem before underscore or camelCase
                parts = [p for p in re.split(r"[_A-Z]", target_name) if len(p) >= 3]
                for part in parts:
                    similar = self.introspect_fixture_names(fixture, part)
                    if similar:
                        break
            if similar:
                hints.append(f"Found related identifiers in the codebase: {similar}. If matching a family of functions, consider a prefix selector like [name^=\"{similar[0]}_\"] or regex [name~=\"{target_name}\"].")

        # 2. Cross-language / Framework naming discrepancies
        if lang == "python" or "python" in (fixture or ""):
            if "__constructor" in selector or "constructor" in selector:
                hints.append("In Python, constructors are named '__init__', not '__constructor'.")
            if ".call#push" in selector:
                hints.append("In Python, list element insertion uses '.call#append' or '.call#extend', not 'push'.")
            if ".call#log" in selector or ".call#println" in selector:
                hints.append("In Python, console output is '.call#print' or '.calls(print)', not 'log' or 'println'.")
            if "finally_statement" in selector:
                hints.append("Use the ASTCSS semantic shorthand '.finally' instead of the raw tree-sitter node type 'finally_statement'.")
            if "if_statement" in selector:
                hints.append("Use the ASTCSS semantic shorthand '.if' instead of the raw node type 'if_statement'.")

        # 3. Attribute vs Name for Module / Receivers
        receiver_match = re.search(r"\.call#([A-Za-z0-9_]+)", selector)
        if receiver_match:
            mod_name = receiver_match.group(1)
            if mod_name in ("json", "os", "sys", "re", "math", "logging", "np", "pd", "fs", "path"):
                hints.append(f"To match method calls on module/object '{mod_name}', use receiver attribute '.call[receiver=\"{mod_name}\"]' rather than function name '.call#{mod_name}'.")

        # 4. Inverted Graph Relations (Callers vs Callees)
        is_callee_intent = any(w in nl_lower for w in ("called by", "calls made by", "invoked by", "callees", "calls out to"))
        is_caller_intent = (
            any(w in nl_lower for w in ("what calls", "who calls", "callers of", "invokes", "references"))
            or bool(re.search(r"\b(what|which)\s+\w+\s+calls?\b", nl_lower))
            or bool(re.search(r"\bcallers?\s+of\b", nl_lower))
        )

        if "::callers" in selector and is_callee_intent:
            hints.append("The intent asks for functions CALLED BY the target (outgoing calls/callees), but '::callers' queries incoming callers. Use '::callees' or child traversal '.fn#... .call'.")
        elif "::callees" in selector and is_caller_intent:
            hints.append("The intent asks for callers invoking the target, but '::callees' queries outgoing calls. Use '::callers'.")

        # 5. Pseudo-class misuse
        if ":decorated" in selector:
            hints.append("Pseudo-class ':decorated' is not supported. Use attribute selector '[annotation*=\"...\"]' or combinator 'decorated_definition > .fn'.")
        if ":typed" in selector:
            hints.append("Pseudo-class ':typed' is not supported. Use signature attribute '[signature=\"...\"]'.")

        return hints

    def build_feedback(self, nl_intent: str, selector: str, exec_result: Dict[str, Any], fixture: Optional[str] = None, lang: str = "python") -> str:
        """Synthesize a complete error diagnostic message for Shot 2 prompt injection."""
        status = exec_result.get("status")
        err_msg = exec_result.get("error_message")
        count = exec_result.get("match_count", 0)

        if status == "parse_error":
            return (
                f"[ASTCSS Syntax Error]\n"
                f"The selector '{selector}' failed to parse: {err_msg}.\n"
                f"Please verify selector syntax (ensure matching brackets, valid combinators '>', '+', '~', ' ', and valid quotes) and output a corrected ASTCSS selector."
            )
        elif status == "unknown_pseudo":
            return (
                f"[ASTCSS Unsupported Pseudo-Class]\n"
                f"The selector '{selector}' used an unknown pseudo-class: {err_msg}.\n"
                f"Please replace it with standard ASTCSS pseudo-classes (:has, :not, :is, :where, :scope, :exported) or attribute matchers ([name=...], [annotation=...], [signature=...])."
            )
        elif status == "empty_match" or count == 0:
            hints = self.diagnose_empty_match(nl_intent, selector, fixture=fixture, lang=lang)
            hint_str = ("\n" + "\n".join(f"- {h}" for h in hints)) if hints else ""
            return (
                f"[Execution Feedback: 0 Matches]\n"
                f"The selector '{selector}' returned 0 matches in the target file AST.{hint_str}\n"
                f"The selector may be too specific, looking for a non-existent identifier, or using the wrong node type. Revise the query to match the intended AST elements."
            )
        elif count > 50:
            sample = ", ".join(exec_result.get("nodes", [])[:3])
            return (
                f"[Execution Feedback: Result Too Broad]\n"
                f"The selector '{selector}' matched {count} nodes (e.g. {sample}...). The query is too broad. Add appropriate scoping, name, or attribute filters."
            )
        else:
            return (
                f"[Execution Feedback]\n"
                f"The selector '{selector}' executed ({count} matches), but did not target the exact requested nodes. Please refine the query constraints."
            )


class ReflexivePromptFormatter:
    """Builds multi-turn ChatML prompt with Shot 1 mistakes and error feedback."""

    @staticmethod
    def format_shot2_prompt(
        system_card: Optional[str],
        nl_intent: str,
        shot1_selector: str,
        feedback_message: str,
        feedback_role: str = "user"  # 'user' or 'environment'
    ) -> str:
        """Construct multi-turn conversation string ready for model inference or training."""
        lines = []
        # Turn 1: User request
        if system_card:
            lines.append(f"<|im_start|>system\n{system_card.strip()}<|im_end|>")
        lines.append(f"<|im_start|>user\n{nl_intent.strip()}<|im_end|>")
        
        # Turn 1 Assistant output
        lines.append(f"<|im_start|>assistant\n{shot1_selector.strip()}<|im_end|>")
        
        # Turn 2: Error Feedback
        lines.append(f"<|im_start|>{feedback_role}\n{feedback_message.strip()}<|im_end|>")
        lines.append("<|im_start|>assistant\n")
        
        return "\n".join(lines)


def evaluate_reflexive_repair(
    model_name: str,
    base_model_path: str,
    adapter_path: Optional[str],
    scores_file: str,
    card_file: str = "card_v1c.md",
    quant: str = "none",
    embed_cpu: bool = False,
    max_repairs: int = 50,
    out_dir: Optional[str] = None
) -> Dict[str, Any]:
    """Take an existing single-shot scores.jsonl run, identify misses, run Shot 2 repair, and measure pass@2."""
    import torch
    from transformers import AutoTokenizer
    from train_qlora import load_model

    engine = ExecutionFeedbackEngine()
    card_text = open(os.path.join(HERE, card_file)).read() if card_file != "none" and os.path.exists(os.path.join(HERE, card_file)) else None

    # Load pairs and scores
    with open(scores_file) as fh:
        scored_rows = [json.loads(l) for l in fh if l.strip()]

    pairs_by_id = {p["id"]: p for p in qualify.load_pairs()}
    misses = [r for r in scored_rows if not r.get("exec_match", False)]

    print(f"\n=======================================================")
    print(f"Reflexive Repair Evaluation: {model_name}")
    print(f"Total Rows: {len(scored_rows)} | Shot 1 Pass: {len(scored_rows) - len(misses)} | Shot 1 Misses: {len(misses)}")
    print(f"Pass@1 Accuracy: {100.0 * (len(scored_rows) - len(misses)) / len(scored_rows):.1f}%")
    print(f"=======================================================\n")

    if not misses:
        return {"pass1": 1.0, "pass2": 1.0, "repaired": 0, "total_misses": 0}

    # Load model for Shot 2 generation
    print(f"Loading {base_model_path} (adapter: {adapter_path})...")
    tok = AutoTokenizer.from_pretrained(base_model_path)
    tok.padding_side = "left"
    model, dev = load_model(base_model_path, embed_cpu, quant)
    if adapter_path:
        from peft import PeftModel
        model = PeftModel.from_pretrained(model, adapter_path)
    model.eval()

    pad = tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id
    stop_ids = sorted({i for i in (tok.convert_tokens_to_ids(prompting.end_of_turn(tok)), tok.eos_token_id,
                                   getattr(model.generation_config, "eos_token_id", None)) if isinstance(i, int)})

    repairs = []
    repaired_count = 0

    for idx, row in enumerate(misses[:max_repairs]):
        pair = pairs_by_id.get(row["id"])
        if not pair:
            continue

        fixture = pair.get("fixture", "py-variety")
        nl_intent = row["nl"]
        shot1_pred = row.get("prediction") or ""

        # Step 1: Diagnose Shot 1 execution
        exec_res = engine.evaluate_selector_on_fixture(fixture, shot1_pred) if shot1_pred else {"status": "parse_error", "error_message": "Empty selector produced", "match_count": 0}
        feedback = engine.build_feedback(nl_intent, shot1_pred, exec_res, fixture=fixture, lang="python")

        # Step 2: Format Shot 2 Prompt
        prompt = ReflexivePromptFormatter.format_shot2_prompt(card_text, nl_intent, shot1_pred, feedback)

        # Step 3: Run Model on Shot 2 Prompt
        enc = tok([prompt], return_tensors="pt", add_special_tokens=False).to(dev)
        t0 = time.time()
        with torch.no_grad():
            out = model.generate(**enc, max_new_tokens=48, do_sample=False, pad_token_id=pad, eos_token_id=stop_ids)
        latency = time.time() - t0

        gen = out[0][enc["input_ids"].shape[1]:]
        shot2_content = tok.decode(gen, skip_special_tokens=True)
        shot2_pred = qualify.extract(shot2_content)

        # Step 4: Evaluate Shot 2 in Engine
        shot2_res = engine.evaluate_selector_on_fixture(fixture, shot2_pred) if shot2_pred else {"status": "parse_error", "nodes": []}
        shot2_match = (V._digest(shot2_res.get("nodes", [])) == pair.get("reference", {}).get("sha256")) if "nodes" in shot2_res else False

        if shot2_match:
            repaired_count += 1
            verdict = "✓ REPAIRED"
        else:
            verdict = "✗ STILL MISS"

        print(f"[{row['id']}] {verdict}")
        print(f"  NL:     {nl_intent}")
        print(f"  Shot 1: {shot1_pred} (Err: {exec_res.get('status')})")
        print(f"  Shot 2: {shot2_pred} (Gold: {pair.get('css')})")
        print(f"  Feedback: {feedback.splitlines()[0]}")
        print()

        repairs.append({
            "id": row["id"],
            "nl": nl_intent,
            "gold": pair.get("css"),
            "shot1_pred": shot1_pred,
            "shot1_status": exec_res.get("status"),
            "feedback": feedback,
            "shot2_pred": shot2_pred,
            "shot2_match": shot2_match,
            "latency_s": round(latency, 2)
        })

    pass1_acc = 100.0 * (len(scored_rows) - len(misses)) / len(scored_rows)
    pass2_acc = 100.0 * (len(scored_rows) - len(misses) + repaired_count) / len(scored_rows)
    recovery_rate = 100.0 * repaired_count / len(misses[:max_repairs]) if misses else 100.0

    print(f"=======================================================")
    print(f"FINAL REFLEXIVE REPAIR RESULTS:")
    print(f"  Pass@1: {pass1_acc:.1f}% ({len(scored_rows) - len(misses)}/{len(scored_rows)})")
    print(f"  Pass@2: {pass2_acc:.1f}% ({len(scored_rows) - len(misses) + repaired_count}/{len(scored_rows)})")
    print(f"  Error Recovery Rate: {recovery_rate:.1f}% ({repaired_count}/{len(misses[:max_repairs])})")
    print(f"=======================================================\n")

    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
        with open(os.path.join(out_dir, "reflexive_repairs.json"), "w") as fh:
            json.dump({
                "model": model_name,
                "pass1_accuracy": pass1_acc,
                "pass2_accuracy": pass2_acc,
                "recovery_rate": recovery_rate,
                "repairs": repairs
            }, fh, indent=2)

    return {
        "pass1": pass1_acc,
        "pass2": pass2_acc,
        "recovery_rate": recovery_rate,
        "repaired_count": repaired_count
    }


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--scores", help="Path to scores.jsonl to run reflexive repair on")
    ap.add_argument("--base", default="/home/teague/.cache/huggingface/hub/models--Qwen--Qwen3.5-0.8B/snapshots/2fc06364715b967f1860aea9cf38778875588b17")
    ap.add_argument("--adapter", default="workspace/adapters/t5-mixed/epoch2")
    ap.add_argument("--name", default="Qwen3.5-0.8B-reflexive")
    ap.add_argument("--card", default="card_v1c.md")
    ap.add_argument("--out", default="runs/reflexive-0.8b-eval")
    args = ap.parse_args()

    if args.scores:
        evaluate_reflexive_repair(
            model_name=args.name,
            base_model_path=args.base,
            adapter_path=args.adapter,
            scores_file=args.scores,
            card_file=args.card,
            out_dir=args.out
        )
    else:
        # Self-diagnostic demo
        engine = ExecutionFeedbackEngine()
        sample_nl = "the update functions"
        sample_pred = ".fn#update"
        diag = engine.evaluate_selector_on_fixture("py-variety", sample_pred)
        fb = engine.build_feedback(sample_nl, sample_pred, diag, fixture="py-variety", lang="python")
        prompt = ReflexivePromptFormatter.format_shot2_prompt("Vocabulary Card...", sample_nl, sample_pred, fb)
        print("--- Demo Reflexive Feedback Prompt ---")
        print(prompt)
