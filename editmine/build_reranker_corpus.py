#!/usr/bin/env python3
"""Build AST Semantic Reranker training dataset (triplets) from harvested code ASTs.

Extracts AST candidate nodes and groups them with semantic intent queries,
pairing relevant nodes (positives) with hard syntactic distractors (negatives).

Output: workspace/datasets/ast-reranker/train.jsonl
"""
import argparse
import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
SETUP_ROOT = os.path.dirname(HERE)
DEFAULT_EDITS = os.path.join(SETUP_ROOT, "workspace", "editmine", "git_edits.jsonl")
DEFAULT_OUT_DIR = os.path.join(SETUP_ROOT, "workspace", "datasets", "ast-reranker")


def extract_code_blocks(code_str, lang):
    """Extract standalone function and class definitions from code."""
    lines = code_str.split("\n")
    blocks = []
    current = []
    
    for line in lines:
        if (line.startswith("def ") or line.startswith("class ") or 
            line.startswith("pub fn ") or line.startswith("fn ") or
            line.startswith("function ") or line.startswith("export function ") or
            line.startswith("func ")):
            if current and len(current) > 2:
                blocks.append("\n".join(current))
            current = [line]
        elif current:
            current.append(line)
            if len(current) > 60:  # Cap length for embedding context
                blocks.append("\n".join(current))
                current = []
                
    if current and len(current) > 2:
        blocks.append("\n".join(current))
    return blocks


def build_reranker_dataset(edits_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    
    print("[*] Reading harvested files and extracting AST code snippets...")
    snippets_by_trait = {
        "error_handling": [],
        "database_query": [],
        "async_network": [],
        "auth_security": [],
        "formatting_logging": []
    }
    
    all_snippets = []
    
    if os.path.exists(edits_path):
        with open(edits_path) as f:
            for line in f:
                if not line.strip():
                    continue
                edit = json.loads(line)
                new_code = edit.get("new", "")
                lang = edit.get("lang", "")
                
                blocks = extract_code_blocks(new_code, lang)
                for b in blocks:
                    all_snippets.append(b)
                    b_lower = b.lower()
                    if "try" in b_lower or "except" in b_lower or "catch" in b_lower or "result<" in b_lower:
                        snippets_by_trait["error_handling"].append(b)
                    if "select" in b_lower or "query" in b_lower or "cursor" in b_lower or "execute(" in b_lower:
                        snippets_by_trait["database_query"].append(b)
                    if "async " in b_lower or "await " in b_lower or "http" in b_lower or "fetch(" in b_lower:
                        snippets_by_trait["async_network"].append(b)
                    if "auth" in b_lower or "token" in b_lower or "password" in b_lower or "permission" in b_lower:
                        snippets_by_trait["auth_security"].append(b)
                    if "logger." in b_lower or "logging." in b_lower or "format(" in b_lower or "print(" in b_lower:
                        snippets_by_trait["formatting_logging"].append(b)

    queries_map = {
        "error_handling": [
            "Functions with explicit try-catch or error recovery handling",
            "Error propagation and exception catching logic"
        ],
        "database_query": [
            "Methods performing SQL queries or database cursor execution",
            "Database query execution and transaction handling functions"
        ],
        "async_network": [
            "Asynchronous functions making network requests or handling I/O",
            "Async coroutines awaiting HTTP or socket responses"
        ],
        "auth_security": [
            "Authentication, token verification, or user authorization checks",
            "Security credential validation and access control handlers"
        ],
        "formatting_logging": [
            "Logging, telemetry instrumentation, and string formatting routines",
            "Event logging and diagnostic message formatting functions"
        ]
    }

    triplets = []
    random.seed(42)
    
    for trait, queries in queries_map.items():
        positives = snippets_by_trait[trait]
        other_snippets = [s for t, snips in snippets_by_trait.items() if t != trait for s in snips]
        if not other_snippets:
            other_snippets = all_snippets
            
        for q in queries:
            for pos in positives[:300]:  # Up to 300 per trait query
                # Pick 3 hard negative distractors from other traits
                negs = random.sample(other_snippets, min(3, len(other_snippets))) if other_snippets else []
                if negs:
                    triplets.append({
                        "query": q,
                        "positive": pos,
                        "negatives": negs
                    })

    out_file = os.path.join(out_dir, "train.jsonl")
    with open(out_file, "w") as out_fh:
        for t in triplets:
            out_fh.write(json.dumps(t, ensure_ascii=False) + "\n")

    manifest = {
        "name": "ast-reranker-triplets-v1",
        "total_triplets": len(triplets),
        "traits": list(queries_map.keys())
    }
    with open(os.path.join(out_dir, "manifest.json"), "w") as mf_fh:
        json.dump(manifest, mf_fh, indent=2)

    print(f"\n[✓] Generated {len(triplets)} AST Semantic Reranker triplets -> {out_file}")


def main():
    parser = argparse.ArgumentParser(description="Build AST reranker triplet dataset")
    parser.add_argument("--edits", default=DEFAULT_EDITS, help="Path to git_edits.jsonl")
    parser.add_argument("--out", default=DEFAULT_OUT_DIR, help="Output directory")
    args = parser.parse_args()

    build_reranker_dataset(args.edits, args.out)


if __name__ == "__main__":
    main()
