#!/usr/bin/env python3
"""Harvest code diffs and commit messages from seed public git repositories.

Clones (or updates) repositories shallowly and extracts before/after file
revisions across commits for all supported languages.

Output: workspace/editmine/git_edits.jsonl
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SETUP_ROOT = os.path.dirname(HERE)
SEED_FILE = os.path.join(HERE, "seed_repos.json")
DEFAULT_CACHE = os.path.join(SETUP_ROOT, "workspace", "repos")
OUT_FILE = os.path.join(SETUP_ROOT, "workspace", "editmine", "git_edits.jsonl")

EXT_TO_LANG = {
    ".py": "python",
    ".rs": "rust",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".cpp": "cpp",
    ".hpp": "cpp",
    ".cc": "cpp",
    ".c": "c",
    ".h": "c",
    ".sql": "sql",
    ".sh": "bash",
    ".bash": "bash",
}


def clone_or_update(url, target_dir, depth=200):
    if os.path.exists(os.path.join(target_dir, ".git")):
        print(f"[*] Updating existing repo in {target_dir}...")
        try:
            subprocess.run(["git", "-C", target_dir, "fetch", "--depth", str(depth)], check=True, capture_output=True)
        except subprocess.CalledProcessError:
            pass
        return
    print(f"[*] Shallow-cloning {url} (depth={depth}) into {target_dir}...")
    os.makedirs(os.path.dirname(target_dir), exist_ok=True)
    subprocess.run(["git", "clone", "--depth", str(depth), url, target_dir], check=True)


def extract_repo_edits(repo_name, repo_dir, max_commits=150):
    """Extract before/after revisions from commits touching single files or small edits."""
    # Get recent commit hashes and subject lines
    res = subprocess.run(
        ["git", "-C", repo_dir, "log", f"-n{max_commits}", "--format=%H%x00%s"],
        capture_output=True, text=True, check=True
    )
    commits = [line.split("\x00", 1) for line in res.stdout.strip().split("\n") if "\x00" in line]
    
    edits = []
    for commit_hash, subject in commits:
        # Get files changed in this commit
        diff_tree = subprocess.run(
            ["git", "-C", repo_dir, "diff-tree", "--no-commit-id", "--name-status", "-r", commit_hash],
            capture_output=True, text=True
        )
        if diff_tree.returncode != 0:
            continue
            
        changes = [l.split("\t") for l in diff_tree.stdout.strip().split("\n") if "\t" in l]
        # Focus on commits touching 1-5 files to isolate focused edits
        if not (1 <= len(changes) <= 5):
            continue

        for change in changes:
            status = change[0]
            if not status.startswith("M") or len(change) < 2:
                continue
            file_path = change[1]
            ext = os.path.splitext(file_path)[1].lower()
            if ext not in EXT_TO_LANG:
                continue
            lang = EXT_TO_LANG[ext]

            # Fetch old and new content
            try:
                old_res = subprocess.run(
                    ["git", "-C", repo_dir, "show", f"{commit_hash}~1:{file_path}"],
                    capture_output=True, text=True, errors="replace"
                )
                new_res = subprocess.run(
                    ["git", "-C", repo_dir, "show", f"{commit_hash}:{file_path}"],
                    capture_output=True, text=True, errors="replace"
                )
                if old_res.returncode != 0 or new_res.returncode != 0:
                    continue
                old_content = old_res.stdout
                new_content = new_res.stdout

                # Filter out gigantic or whitespace-only files
                if len(old_content) > 50000 or len(new_content) > 50000:
                    continue
                if old_content.strip() == new_content.strip():
                    continue

                edits.append({
                    "repo": repo_name,
                    "commit": commit_hash[:10],
                    "message": subject,
                    "file_path": file_path,
                    "lang": lang,
                    "ext": ext,
                    "old": old_content,
                    "new": new_content
                })
            except Exception:
                continue

    return edits


def main():
    parser = argparse.ArgumentParser(description="Harvest code revisions from public repos")
    parser.add_argument("--cache-dir", default=DEFAULT_CACHE, help="Directory to store cloned repos")
    parser.add_argument("--out", default=OUT_FILE, help="Output JSONL path")
    parser.add_argument("--depth", type=int, default=150, help="Git shallow clone depth")
    parser.add_argument("--limit-repos", type=int, default=0, help="Limit number of repos for smoke testing")
    args = parser.parse_args()

    os.makedirs(args.cache_dir, exist_ok=True)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)

    with open(SEED_FILE) as f:
        seed_data = json.load(f)

    all_repos = []
    for lang, repos in seed_data.items():
        for r in repos:
            all_repos.append(r)

    if args.limit_repos:
        all_repos = all_repos[:args.limit_repos]

    total_edits = 0
    with open(args.out, "w") as out_fh:
        for item in all_repos:
            repo_name = item["repo"]
            repo_url = item["url"]
            repo_dir = os.path.join(args.cache_dir, repo_name.replace("/", "_"))
            try:
                clone_or_update(repo_url, repo_dir, depth=args.depth)
                edits = extract_repo_edits(repo_name, repo_dir, max_commits=args.depth)
                print(f"[+] {repo_name}: extracted {len(edits)} modified file pairs")
                for e in edits:
                    out_fh.write(json.dumps(e, ensure_ascii=False) + "\n")
                total_edits += len(edits)
            except Exception as ex:
                print(f"[-] Error processing {repo_name}: {ex}")

    print(f"\n[✓] Done! Harvested {total_edits} total before/after file revisions -> {args.out}")


if __name__ == "__main__":
    main()
