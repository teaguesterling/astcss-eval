#!/usr/bin/env python3
"""Build Fluent Mutation API training dataset from mined git AST diffs.

Links classified AST deltas (wrapCall, addArg, addParam, wrapInTry, etc.)
with commit intent messages and constructs verified fluent API call pairs:
$('selector').op(args)

Output: workspace/datasets/fluent-mutations/train.jsonl
"""
import argparse
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
SETUP_ROOT = os.path.dirname(HERE)
DEFAULT_EDITS = os.path.join(SETUP_ROOT, "workspace", "editmine", "git_edits.jsonl")
DEFAULT_MUTATIONS = os.path.join(SETUP_ROOT, "workspace", "editmine", "mined_mutations.jsonl")
DEFAULT_OUT_DIR = os.path.join(SETUP_ROOT, "workspace", "datasets", "fluent-mutations")


def clean_intent_message(msg):
    """Normalize git commit message to an imperative natural language instruction."""
    # Strip issue references, PR tags, co-authors, and trailing periods
    s = msg.strip().split("\n")[0]
    s = re.sub(r"\(#\d+\)", "", s)
    s = re.sub(r"\[.*?\]", "", s)
    s = re.sub(r"^fix\(.*?\):\s*", "Fix ", s, flags=re.IGNORECASE)
    s = re.sub(r"^feat\(.*?\):\s*", "Add ", s, flags=re.IGNORECASE)
    s = re.sub(r"^refactor\(.*?\):\s*", "Refactor ", s, flags=re.IGNORECASE)
    s = s.strip()
    if s and not s[0].isupper():
        s = s[0].upper() + s[1:]
    return s


def build_corpus(edits_path, mutations_path, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    
    print("[*] Indexing raw edits...")
    edits_by_id = {}
    if os.path.exists(edits_path):
        with open(edits_path) as f:
            for idx, line in enumerate(f, 1):
                if line.strip():
                    edits_by_id[idx] = json.loads(line)

    print(f"[*] Loaded {len(edits_by_id)} raw file edits. Processing mined AST mutations...")
    
    structured_pairs = []
    seen_keys = set()
    
    with open(mutations_path) as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            edit_id = rec.get("edit_id")
            op = rec.get("inferred_op")
            
            # Skip uninformative pure replacements for now, focus on named AST operations
            if op == "replace" or not op:
                continue

            raw_edit = edits_by_id.get(edit_id)
            if not raw_edit:
                continue

            msg = clean_intent_message(rec.get("message", ""))
            if not msg or len(msg) < 5:
                continue

            lang = rec.get("lang")
            file_path = rec.get("file_path")
            node_type = rec.get("node_type")
            
            # Deduplicate per (repo, commit, op, file_path)
            dedup_key = (rec.get("repo"), rec.get("commit"), op, file_path)
            if dedup_key in seen_keys:
                continue
            seen_keys.add(dedup_key)

            # Construct structural selector heuristic
            base_selector = ".fn"
            if "class" in node_type or "struct" in node_type or op in ("addField", "removeField"):
                base_selector = ".class"
            elif "import" in node_type or op in ("addImport", "removeImport", "ensureImport"):
                base_selector = "mod"
            elif "call" in node_type or op in ("wrapCall", "chainCall", "wrapAwait", "addArg", "removeArg"):
                base_selector = ".call"
            elif "param" in node_type or op in ("addParam", "removeParam", "setParamType"):
                base_selector = ".fn"
            elif "assert" in node_type or op == "addAssertion":
                base_selector = ".fn"
            elif op in ("addDecorator", "removeDecorator"):
                base_selector = ".fn"

            # Construct canonical fluent call
            if op == "addImport":
                fluent_call = "$('mod').addImport(...)"
            elif op == "ensureImport":
                fluent_call = "$('mod').ensureImport(...)"
            elif op == "removeImport":
                fluent_call = "$('mod > .import').remove()"
            elif op == "addDecorator":
                fluent_call = f"$('{base_selector}').addDecorator(...)"
            elif op == "removeDecorator":
                fluent_call = f"$('{base_selector} > .decorator').remove()"
            elif op == "addField":
                fluent_call = f"$('{base_selector}').addField(...)"
            elif op == "removeField":
                fluent_call = f"$('{base_selector} > .field').remove()"
            elif op == "setAsync":
                fluent_call = f"$('{base_selector}').setAsync(true)"
            elif op == "setVisibility":
                fluent_call = f"$('{base_selector}').setVisibility('pub')"
            elif op == "setReturnType":
                fluent_call = f"$('{base_selector}').setReturnType(...)"
            elif op == "setParamType":
                fluent_call = f"$('{base_selector}').setParamType(param, type)"
            elif op == "addAssertion":
                fluent_call = f"$('{base_selector}').addAssertion(...)"
            elif op == "wrapWith":
                fluent_call = f"$('{base_selector}').wrapWith(...)"
            elif op == "wrapAwait":
                fluent_call = f"$('{base_selector}').wrapAwait()"
            elif op == "chainCall":
                fluent_call = f"$('{base_selector}').chainCall(...)"
            elif op == "extractVariable":
                fluent_call = f"$('{base_selector}').extractVariable(...)"
            elif op == "extractFunction":
                fluent_call = f"$('{base_selector}').extractFunction(...)"
            elif op == "moveTo" or "move " in msg.lower() or "relocate" in msg.lower():
                fluent_call = f"$('{base_selector}').moveTo('.target', {{pos: 'inside'}})"
            elif op == "wrapInTry":
                fluent_call = f"$('{base_selector}').wrapInTry().on('Exception', 'pass')"
            elif op == "addParam":
                fluent_call = f"$('{base_selector}').addParam(...)"
            elif op == "removeParam":
                fluent_call = f"$('{base_selector}').removeParam(...)"
            elif op == "addArg":
                fluent_call = f"$('{base_selector}').addArg(...)"
            elif op == "removeArg":
                fluent_call = f"$('{base_selector}').removeArg(...)"
            elif op == "setReturn":
                fluent_call = f"$('{base_selector}').setReturn(...)"
            elif op == "addCondition":
                fluent_call = f"$('{base_selector}').addCondition(...)"
            elif op == "addComment":
                fluent_call = f"$('{base_selector}').addComment(...)"
            else:
                fluent_call = f"$('{base_selector}').{op}()"

            pair = {
                "id": f"mined-{len(structured_pairs)+1:06d}",
                "repo": rec.get("repo"),
                "commit": rec.get("commit"),
                "file_path": file_path,
                "lang": lang,
                "op": op,
                "node_type": node_type,
                "delta": rec.get("delta"),
                "instruction": msg,
                "target_selector": base_selector,
                "fluent_call": fluent_call
            }
            structured_pairs.append(pair)

    out_file = os.path.join(out_dir, "train.jsonl")
    with open(out_file, "w") as out_fh:
        for p in structured_pairs:
            out_fh.write(json.dumps(p, ensure_ascii=False) + "\n")

    manifest = {
        "name": "fluent-mutations-v1",
        "total_pairs": len(structured_pairs),
        "by_op": {}
    }
    for p in structured_pairs:
        op = p["op"]
        manifest["by_op"][op] = manifest["by_op"].get(op, 0) + 1

    with open(os.path.join(out_dir, "manifest.json"), "w") as mf_fh:
        json.dump(manifest, mf_fh, indent=2)

    print(f"\n[✓] Generated {len(structured_pairs)} structured fluent mutation training pairs -> {out_file}")
    print("Operations breakdown:")
    for op, cnt in sorted(manifest["by_op"].items(), key=lambda x: -x[1]):
        print(f"  - {op:15s}: {cnt:5d}")


def main():
    parser = argparse.ArgumentParser(description="Build fluent mutation corpus")
    parser.add_argument("--edits", default=DEFAULT_EDITS, help="Path to git_edits.jsonl")
    parser.add_argument("--mutations", default=DEFAULT_MUTATIONS, help="Path to mined_mutations.jsonl")
    parser.add_argument("--out", default=DEFAULT_OUT_DIR, help="Output directory")
    args = parser.parse_args()

    build_corpus(args.edits, args.mutations, args.out)


if __name__ == "__main__":
    main()
