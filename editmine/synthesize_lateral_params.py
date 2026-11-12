#!/usr/bin/env python3
"""Synthesize training pairs for BOTH Inline Literal and Lateral Parameter / File Reference options.

Option A: Inline direct literals (e.g. replaceWith("return None"), addImport("import os"))
Option B: Lateral parameter references (e.g. replaceWith(params.new_impl), append(fromFile("methods.py")))
"""
import argparse
import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
SETUP_ROOT = os.path.dirname(HERE)
DEFAULT_OUT = os.path.join(SETUP_ROOT, "workspace", "datasets", "fluent-mutations")

FUNCS = ['process_order', 'calculate_tax', 'validate_token', 'handle_request', 'format_output', 'fetch_user', 'parse_payload', 'sanitize_query', 'init_connection']
CLASSES = ['OrderProcessor', 'TaxCalculator', 'AuthManager', 'RequestHandler', 'DataFormatter', 'UserManager', 'ConnectionPool']
PARAMS = ['new_implementation', 'handler_code', 'method_body', 'replacement', 'helper_code', 'sanitized_logic', 'async_version', 'custom_hook', 'auth_logic']
FILES = ['snippets/new_handler.py', 'src/auth_methods.py', 'templates/boilerplate.rs', 'generated/schema_types.ts', 'handlers/fallback.go', 'common/imports.py', 'license_header.txt']

PATTERNS = [
    # replaceWith (lateral vs inline)
    (
        "Replace the {fn} function with the {param} parameter",
        "$('.fn#{fn}').replaceWith(params.{param})"
    ),
    (
        "Replace method {fn} in class {cls} with code from {file}",
        "$('.class#{cls} .fn#{fn}').replaceWith(fromFile('{file}'))"
    ),
    (
        "Replace body of {fn} with inline return True",
        "$('.fn#{fn}').replaceWith('return True')"
    ),
    (
        "Substitute {fn} using the {param} argument",
        "$('.fn#{fn}').replaceWith(params.{param})"
    ),
    (
        "Overwrite function {fn} using the implementation in file {file}",
        "$('.fn#{fn}').replaceWith(fromFile('{file}'))"
    ),
    
    # append / prepend (lateral vs inline)
    (
        "Append methods from parameter {param} into class {cls}",
        "$('.class#{cls}').append(params.{param})"
    ),
    (
        "Append new helper methods from {file} into {cls}",
        "$('.class#{cls}').append(fromFile('{file}'))"
    ),
    (
        "Prepend license header from {file} to the module",
        "$('mod').prepend(fromFile('{file}'))"
    ),
    (
        "Append parameter {param} to the end of module",
        "$('mod').append(params.{param})"
    ),
    (
        "Prepend boilerplate code from {file} to class {cls}",
        "$('.class#{cls}').prepend(fromFile('{file}'))"
    ),

    # insertBefore / insertAfter
    (
        "Insert the code from parameter {param} immediately before {fn}",
        "$('.fn#{fn}').insertBefore(params.{param})"
    ),
    (
        "Insert the snippet from {file} after the imports",
        "$('mod > .import:last').insertAfter(fromFile('{file}'))"
    ),
    (
        "Insert helper logic from parameter {param} before class {cls}",
        "$('.class#{cls}').insertBefore(params.{param})"
    ),

    # addImport / ensureImport
    (
        "Add module imports from parameter {param}",
        "$('mod').addImport(params.{param})"
    ),
    (
        "Ensure imports from file {file} are added to module",
        "$('mod').ensureImport(fromFile('{file}'))"
    ),

    # addField / addDecorator / wrapWith
    (
        "Add field definitions from parameter {param} to class {cls}",
        "$('.class#{cls}').addField(params.{param})"
    ),
    (
        "Wrap function {fn} with the context manager supplied in parameter {param}",
        "$('.fn#{fn}').wrapWith(params.{param})"
    ),
    (
        "Add decorators from parameter {param} to function {fn}",
        "$('.fn#{fn}').addDecorator(params.{param})"
    ),

    # evalSnippet with lateral inputs
    (
        "Run the {fn} function using input payload parameter {param}",
        "$('.fn#{fn}').evalSnippet(params.{param})"
    ),
    (
        "Evaluate {fn} with test fixtures from file {file}",
        "$('.fn#{fn}').evalSnippet(fromFile('{file}'))"
    )
]


def generate_lateral_pairs(count=2500, seed=42):
    random.seed(seed)
    pairs = []
    
    for i in range(count):
        pat_nl, pat_fluent = random.choice(PATTERNS)
        fn = random.choice(FUNCS)
        cls_name = random.choice(CLASSES)
        param = random.choice(PARAMS)
        fpath = random.choice(FILES)
        
        nl = pat_nl.format(fn=fn, cls=cls_name, param=param, file=fpath)
        fluent = pat_fluent.format(fn=fn, cls=cls_name, param=param, file=fpath)
        
        nl = nl[0].upper() + nl[1:] if nl else nl
        
        pairs.append({
            "id": f"lateral-{i+1:06d}",
            "type": "lateral_or_inline",
            "instruction": nl,
            "fluent_call": fluent
        })
        
    return pairs


def build_and_merge(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    lateral_pairs = generate_lateral_pairs(count=2500)
    
    card_path = os.path.join(SETUP_ROOT, "mutator", "card_mut.md")
    card_text = open(card_path).read() if os.path.exists(card_path) else ""
    
    # Load current dataset
    existing_file = os.path.join(out_dir, "train.jsonl")
    existing_pairs = []
    if os.path.exists(existing_file):
        with open(existing_file) as f:
            for line in f:
                if line.strip():
                    try:
                        existing_pairs.append(json.loads(line))
                    except Exception:
                        pass
                        
    print(f"[*] Loaded {len(existing_pairs)} existing train rows.")
    
    # Convert lateral pairs to chat rows
    new_chat_rows = []
    for p in lateral_pairs:
        new_chat_rows.append({
            "messages": [
                {"role": "system", "content": card_text},
                {"role": "user", "content": p["instruction"]},
                {"role": "assistant", "content": p["fluent_call"]}
            ],
            "pair_id": p["id"],
            "type": "lateral_or_inline"
        })
        
    all_rows = existing_pairs + new_chat_rows
    random.Random(18).shuffle(all_rows)
    
    n_val = max(100, int(len(all_rows) * 0.1))
    val_rows = all_rows[:n_val]
    train_rows = all_rows[n_val:]
    
    with open(os.path.join(out_dir, "train.jsonl"), "w") as f:
        for r in train_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            
    with open(os.path.join(out_dir, "val.jsonl"), "w") as f:
        for r in val_rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            
    manifest = {
        "name": "fluent-mutations-tools-and-lateral-v3",
        "total_rows": len(all_rows),
        "train_rows": len(train_rows),
        "val_rows": len(val_rows),
        "lateral_param_pairs": len(lateral_pairs)
    }
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
        
    print(f"[✓] Successfully generated and merged dataset:")
    print(f"    - Total rows: {len(all_rows)}")
    print(f"    - Training rows: {len(train_rows)}")
    print(f"    - Validation rows: {len(val_rows)}")
    print(f"    - Added lateral & file reference pairs: {len(lateral_pairs)}")


def main():
    parser = argparse.ArgumentParser(description="Synthesize lateral parameter pairs and merge")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output directory")
    args = parser.parse_args()
    build_and_merge(args.out)


if __name__ == "__main__":
    main()
