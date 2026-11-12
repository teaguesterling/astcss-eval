#!/bin/bash
# End-to-end repository mining pipeline:
# 1. Clones seed public repos across Python, Rust, TS, Go, C++, SQL
# 2. Extracts before/after file revisions across commits (git_edits.jsonl)
# 3. Parses ASTs in DuckDB and classifies structural mutations (mined_mutations.jsonl)
set -euo pipefail
cd "$(dirname "$0")/.."

L=$PWD/workspace/editmine
mkdir -p "$L"

echo "[1/2] Harvesting git commits from seed public repositories..."
python3 editmine/harvest_git_edits.py --depth 150 --out "$L/git_edits.jsonl"

echo "[2/2] Mining AST diffs and classifying fluent operations in DuckDB..."
python3 editmine/ast_diff_miner.py --input "$L/git_edits.jsonl" --out "$L/mined_mutations.jsonl"

echo "[✓] Full harvest complete! Output: $L/mined_mutations.jsonl"
