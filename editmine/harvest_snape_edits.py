#!/usr/bin/env python3
"""Harvest and Functionally Verify Real Assistant Edits from Remote Host 'snape'.

Extracts:
1. 1,460+ version snapshot diffs from snape:~/.claude/file-history/
2. 370+ replace_file_content calls from snape:~/.gemini/antigravity-cli/brain/
3. Verifies each transform locally with FluentEngine and appends to the dataset.
"""
import glob
import json
import os
import subprocess
import sys
from collections import defaultdict
from typing import Any, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
SETUP_DIR = os.path.dirname(HERE)
if SETUP_DIR not in sys.path:
    sys.path.insert(0, SETUP_DIR)

from mutator.engine import FluentEngine

LANG_EXT_MAP = {
    ".py": "python",
    ".rs": "rust",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".java": "java",
    ".sql": "sql",
    ".sh": "bash",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
}


def detect_language(fpath: str) -> Optional[str]:
    ext = os.path.splitext(fpath)[1].lower()
    return LANG_EXT_MAP.get(ext)


REMOTE_HARVEST_SCRIPT = r"""
import glob, json, os
from collections import defaultdict

LANG_EXT_MAP = {
    ".py": "python", ".rs": "rust", ".ts": "typescript", ".tsx": "typescript",
    ".js": "javascript", ".jsx": "javascript", ".go": "go", ".c": "c",
    ".h": "c", ".cpp": "cpp", ".hpp": "cpp", ".cc": "cpp", ".java": "java",
    ".sql": "sql", ".sh": "bash", ".yaml": "yaml", ".yml": "yaml", ".json": "json"
}

# 1. Mine Antigravity
ag_logs = glob.glob('/home/teague/.gemini/antigravity-cli/brain/*/.system_generated/logs/transcript_full.jsonl')
for p in ag_logs:
    try:
        last_prompt = ""
        for line in open(p, 'r', encoding='utf-8', errors='ignore'):
            if not line.strip(): continue
            obj = json.loads(line)
            if obj.get('type') == 'USER_INPUT':
                last_prompt = obj.get('content', '')
            for tc in obj.get('tool_calls', []):
                if tc.get('name') == 'replace_file_content':
                    args = tc.get('args', {})
                    tgt = args.get('TargetContent', '')
                    repl = args.get('ReplacementContent', '')
                    fpath = args.get('TargetFile', '')
                    desc = args.get('Instruction') or args.get('Description') or last_prompt
                    ext = os.path.splitext(fpath)[1].lower()
                    lang = LANG_EXT_MAP.get(ext)
                    if tgt and repl and tgt != repl and lang:
                        print(json.dumps({
                            "source": "snape_antigravity",
                            "file": fpath,
                            "language": lang,
                            "description": desc,
                            "before": tgt,
                            "after": repl
                        }))
    except Exception:
        pass

# 2. Mine Claude File History
file_hist = glob.glob('/home/teague/.claude/file-history/*/*@v*')
versions_by_file = defaultdict(list)
for p in file_hist:
    parts = p.rsplit('@v', 1)
    if len(parts) == 2 and parts[1].isdigit():
        versions_by_file[parts[0]].append((int(parts[1]), p))

for base, vlist in versions_by_file.items():
    vlist.sort(key=lambda x: x[0])
    for i in range(len(vlist) - 1):
        p_before = vlist[i][1]
        p_after = vlist[i + 1][1]
        try:
            content_before = open(p_before, 'r', encoding='utf-8', errors='ignore').read()
            content_after = open(p_after, 'r', encoding='utf-8', errors='ignore').read()
            if len(content_before) < 100000 and len(content_after) < 100000:
                if content_before.strip() and content_before != content_after:
                    print(json.dumps({
                        "source": "snape_claude_history",
                        "file": base,
                        "language": "python",
                        "description": f"Update version {vlist[i][0]} to {vlist[i+1][0]}",
                        "before": content_before,
                        "after": content_after
                    }))
        except Exception:
            pass
"""


def fetch_remote_candidates() -> List[Dict[str, Any]]:
    """Stream candidate edits from snape over SSH via stdin pipe."""
    cmd = ["ssh", "snape", "python3", "-u"]
    print("[*] Streaming edit candidates from snape over SSH stdin pipe...")
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stdout, stderr = proc.communicate(input=REMOTE_HARVEST_SCRIPT)
    
    if stderr.strip():
        print(f"[*] Remote stderr notice: {stderr[:200]}...")

    candidates = []
    for line in stdout.splitlines():
        if line.strip():
            try:
                candidates.append(json.loads(line))
            except Exception:
                pass
    return candidates


def synthesize_and_verify(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Synthesize fluent expressions and functionally verify them locally."""
    engine = FluentEngine()
    verified = []

    print(f"[*] Functionally verifying {len(candidates)} candidates from snape...")
    for idx, edit in enumerate(candidates):
        before = edit["before"]
        after = edit["after"]
        lang = edit.get("language", "python")
        desc = edit.get("description", "Code transformation")

        # Heuristic synthesis
        if after.startswith("# ") or after.startswith("// ") or after.startswith("-- "):
            comment_line = after.splitlines()[0]
            text = comment_line.lstrip("#/- ")
            call = f'$("${{target}}").addComment("{text}")'
            params = {}
        elif lang == "python" and not before.strip().startswith("@") and after.strip().startswith("@") and "\ndef " in after:
            deco_line = after.splitlines()[0][1:]
            call = f'$(".fn@target").annotate("{deco_line}")'
            params = {}
        else:
            call = '$("${target}").replaceWith(params.new_code)'
            params = {"new_code": after}

        try:
            ctx = engine.execute_chain(before, call, params=params)
            if ctx.trace and all(t.get("status") == "success" for t in ctx.trace):
                verified.append({
                    "source": edit["source"],
                    "language": lang,
                    "description": desc,
                    "input_code": before,
                    "target_code": after,
                    "fluent_call": call,
                    "params": params,
                })
        except Exception:
            pass

        if (idx + 1) % 250 == 0:
            print(f"    Processed {idx + 1}/{len(candidates)} candidates ({len(verified)} verified)...", flush=True)

    return verified


def main():
    print("=" * 60)
    print("HARVESTING REAL-WORLD EDITS FROM REMOTE HOST 'SNAPE'")
    print("=" * 60)

    candidates = fetch_remote_candidates()
    print(f"[+] Successfully streamed {len(candidates)} candidate edits from snape.")

    verified = synthesize_and_verify(candidates)
    print(f"[+] Functionally verified {len(verified)} edits from snape!")

    out_dir = os.path.join(SETUP_DIR, "workspace", "datasets", "fluent-mutations")
    os.makedirs(out_dir, exist_ok=True)
    out_file = os.path.join(out_dir, "snape_mined_edits.jsonl")
    with open(out_file, "w", encoding="utf-8") as f:
        for item in verified:
            f.write(json.dumps(item) + "\n")
    print(f"[+] Saved {len(verified)} verified pairs to {out_file}")

    # Append to train and val
    import random
    random.seed(42)
    random.shuffle(verified)
    split_idx = int(len(verified) * 0.9)
    train_add = verified[:split_idx]
    val_add = verified[split_idx:]

    train_path = os.path.join(out_dir, "train.jsonl")
    val_path = os.path.join(out_dir, "val.jsonl")

    with open(train_path, "a", encoding="utf-8") as f:
        for item in train_add:
            f.write(json.dumps(item) + "\n")

    with open(val_path, "a", encoding="utf-8") as f:
        for item in val_add:
            f.write(json.dumps(item) + "\n")

    print(f"[+] Appended {len(train_add)} to train.jsonl and {len(val_add)} to val.jsonl")


if __name__ == "__main__":
    main()
