#!/usr/bin/env python3
"""Synthesize training pairs for Secondary Fluent API Tools:
1. Runtime & Sandboxed Execution (evalSnippet, dryRun)
2. Scope & Binding Analysis (inspectScope, freeVariables, capturedBindings)
3. Test Coverage & Impact (coveringTests, runTests)
4. Debugging & Observability (setBreakpoint, traceCalls)
5. Hygiene & Formatting (reformat, typeCheck, lint)
6. Slicing & Dependencies (backwardSlice, forwardSlice)

Outputs structured pairs formatted for chat training.
"""
import argparse
import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
SETUP_ROOT = os.path.dirname(HERE)
DEFAULT_OUT = os.path.join(SETUP_ROOT, "workspace", "datasets", "fluent-mutations")

TEMPLATES = [
    # 1. Execution
    {
        "category": "execution",
        "op": "evalSnippet",
        "patterns": [
            ("Run the helper function {fn} with input {input_val}", "$('.fn#{fn}').evalSnippet({inputs})"),
            ("Execute the {fn} method with mock parameters {input_val}", "$('.class .fn#{fn}').evalSnippet({inputs})"),
            ("Evaluate the loop inside {fn} in a sandboxed interpreter", "$('.fn#{fn} > .loop').evalSnippet({inputs})"),
            ("Test run the calculation {expr} with {inputs}", "$('.call#{expr}').evalSnippet({inputs})"),
            ("Dry run the function {fn} with simulated context", "$('.fn#{fn}').dryRun({inputs})"),
        ],
        "inputs_samples": ['{"x": 10, "y": 20}', '{"items": [1, 2, 3]}', '{"user_id": "u123", "active": True}', '{"timeout": 5.0}', '{}']
    },
    # 2. Scope & Variables
    {
        "category": "scope",
        "op": "inspectScope",
        "patterns": [
            ("Show all variables in scope at the start of {fn}", "$('.fn#{fn}').inspectScope()"),
            ("Inspect visible identifiers inside the loop in {fn}", "$('.fn#{fn} > .loop').inspectScope()"),
            ("Find all free variables used in helper {fn}", "$('.fn#{fn}').freeVariables()"),
            ("List all captured closure variables in the callback", "$('.fn:has(.call) lambda').capturedBindings()"),
            ("What bindings are available inside the except block of {fn}", "$('.fn#{fn} .catch').inspectScope()"),
            ("Identify all global and imported symbols referenced in {fn}", "$('.fn#{fn}').inspectScope({{filter: 'imports'}})"),
        ],
        "inputs_samples": ['{}']
    },
    # 3. Testing & Verification
    {
        "category": "testing",
        "op": "coveringTests",
        "patterns": [
            ("Find all unit tests that execute {fn}", "$('.fn#{fn}').coveringTests()"),
            ("Which test cases cover the authentication check in {fn}", "$('.fn#{fn} .if').coveringTests()"),
            ("Run only the tests that cover method {fn}", "$('.fn#{fn}').runTests()"),
            ("Find test coverage for error handlers in {fn}", "$('.fn#{fn} .catch').coveringTests()"),
            ("List test suite impact for modifying class {cls}", "$('.class#{cls}').coveringTests()"),
        ],
        "inputs_samples": ['{}']
    },
    # 4. Debugging & Breakpoints
    {
        "category": "debugging",
        "op": "setBreakpoint",
        "patterns": [
            ("Set a breakpoint on function {fn}", "$('.fn#{fn}').setBreakpoint()"),
            ("Set a conditional breakpoint in {fn} when {cond}", "$('.fn#{fn}').setBreakpoint('{cond}')"),
            ("Attach a call tracer to all calls to {fn}", "$('.call#{fn}').traceCalls()"),
            ("Profile memory and execution time for {fn}", "$('.fn#{fn}').profile()"),
            ("Set a breakpoint at the exception handler in {fn}", "$('.fn#{fn} .catch').setBreakpoint()"),
        ],
        "inputs_samples": ['{}'],
        "cond_samples": ['count > 100', 'err is not None', 'status != 200', 'retries == 0']
    },
    # 5. Hygiene & Formatting
    {
        "category": "hygiene",
        "op": "reformat",
        "patterns": [
            ("Reformat function {fn} using {style}", "$('.fn#{fn}').reformat('{style}')"),
            ("Format class {cls} cleanly", "$('.class#{cls}').reformat()"),
            ("Run type checker on {fn}", "$('.fn#{fn}').typeCheck()"),
            ("Check linter diagnostics for module imports", "$('mod > .import').lint()"),
            ("Format the SQL query block inside {fn}", "$('.fn#{fn} .str[name*=\"SQL\"]').reformat('sql')"),
        ],
        "styles": ['black', 'prettier', 'rustfmt', 'gofmt', 'default']
    },
    # 6. Slicing & Dependencies
    {
        "category": "slicing",
        "op": "backwardSlice",
        "patterns": [
            ("Find all lines influencing variable {var} in {fn}", "$('.fn#{fn} .var#{var}').backwardSlice()"),
            ("Extract backward dependency slice for {var}", "$('.var#{var}').backwardSlice()"),
            ("Show forward data flow affected by {var}", "$('.var#{var}').forwardSlice()"),
            ("Find all control dependencies of return statement in {fn}", "$('.fn#{fn} .jump#return').controlDependencies()"),
        ],
        "vars": ['result', 'total', 'user', 'payload', 'status', 'token', 'idx', 'db_conn']
    }
]

FUNCS = ['calculate_total', 'process_request', 'validate_user', 'fetch_data', 'handle_event', 'transform_payload', 'parse_config', 'execute_job', 'render_template', 'sanitize_input']
CLASSES = ['UserService', 'QueryExecutor', 'DataPipeline', 'AuthenticationHandler', 'CacheManager', 'ConfigParser']


def generate_pairs(count=1800, seed=42):
    random.seed(seed)
    pairs = []
    
    for i in range(count):
        tpl_group = random.choice(TEMPLATES)
        cat = tpl_group["category"]
        op = tpl_group["op"]
        pat_nl, pat_fluent = random.choice(tpl_group["patterns"])
        
        fn = random.choice(FUNCS)
        cls_name = random.choice(CLASSES)
        inp = random.choice(tpl_group.get("inputs_samples", ['{}']))
        cond = random.choice(tpl_group.get("cond_samples", ['retries > 3']))
        style = random.choice(tpl_group.get("styles", ['black']))
        var = random.choice(tpl_group.get("vars", ['result']))
        
        nl = pat_nl.format(fn=fn, cls=cls_name, input_val=inp, inputs=inp, cond=cond, style=style, var=var, expr=fn)
        fluent = pat_fluent.format(fn=fn, cls=cls_name, inputs=inp, cond=cond, style=style, var=var, expr=fn)
        
        # Capitalize first letter
        nl = nl[0].upper() + nl[1:] if nl else nl
        
        pair = {
            "id": f"secondary-{i+1:06d}",
            "category": cat,
            "op": op,
            "instruction": nl,
            "target_selector": fluent.split(").")[0].replace("$(", "").strip("'\""),
            "fluent_call": fluent
        }
        pairs.append(pair)
        
    return pairs


def build_and_merge(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    secondary_pairs = generate_pairs(count=2000)
    
    card_path = os.path.join(SETUP_ROOT, "mutator", "card_mut.md")
    card_text = open(card_path).read() if os.path.exists(card_path) else ""
    
    # Load existing mined pairs
    existing_file = os.path.join(out_dir, "train.jsonl")
    existing_pairs = []
    if os.path.exists(existing_file):
        with open(existing_file) as f:
            for line in f:
                if line.strip():
                    try:
                        rec = json.loads(line)
                        if "messages" in rec:
                            existing_pairs.append(rec)
                        elif "fluent_call" in rec:
                            # Format into chat row
                            existing_pairs.append({
                                "messages": [
                                    {"role": "system", "content": card_text},
                                    {"role": "user", "content": rec["instruction"]},
                                    {"role": "assistant", "content": rec["fluent_call"]}
                                ],
                                "pair_id": rec.get("id"),
                                "op": rec.get("op", "mutation")
                            })
                    except Exception:
                        pass
                        
    print(f"[*] Loaded {len(existing_pairs)} existing pairs.")
    
    # Convert secondary pairs to chat rows
    sec_chat_rows = []
    for p in secondary_pairs:
        sec_chat_rows.append({
            "messages": [
                {"role": "system", "content": card_text},
                {"role": "user", "content": p["instruction"]},
                {"role": "assistant", "content": p["fluent_call"]}
            ],
            "pair_id": p["id"],
            "op": p["op"],
            "category": p["category"]
        })
        
    all_rows = existing_pairs + sec_chat_rows
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
        "name": "fluent-mutations-and-tools-v2",
        "total_rows": len(all_rows),
        "train_rows": len(train_rows),
        "val_rows": len(val_rows),
        "mined_structural_pairs": len(existing_pairs),
        "secondary_tool_pairs": len(secondary_pairs)
    }
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
        
    print(f"[✓] Created dataset with {len(train_rows)} train rows and {len(val_rows)} val rows in {out_dir}")
    print(f"    - Mined AST Mutations: {len(existing_pairs)}")
    print(f"    - Secondary Tool Pairs: {len(secondary_pairs)}")


def main():
    parser = argparse.ArgumentParser(description="Synthesize secondary tool pairs and merge")
    parser.add_argument("--out", default=DEFAULT_OUT, help="Output directory")
    args = parser.parse_args()
    build_and_merge(args.out)


if __name__ == "__main__":
    main()
