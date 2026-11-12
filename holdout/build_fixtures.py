"""Build the holdout fixture set: repos that appear in NO training fixture.

Rules this enforces, because a holdout that leaks is worse than none:
  - a repo used by train/fixtures or fixtures/ is excluded, AND so is any WORKTREE VARIANT of
    one (magic-trees is magic, lackpy-fix-ast-whitelist is lackpy, duck_block_utils-fix-b4 is
    duck_block_utils). Same code under a different directory name is the same code.
  - 11 languages, of which typescript and ruby appear in NO training fixture at all, so the
    suite measures both generalisation to new repos in a known language and transfer to an
    unknown one.
  - files are capped per fixture: verify.py needs references in 1..50 nodes, which a huge
    fixture makes nearly impossible, and every ast_select_from costs ~6 s of planning.
"""
import hashlib, json, os, shutil, subprocess

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(HERE, "holdout/fixtures")
ROOT = "/home/teague/Projects"

#: (fixture name, repo dir, language, file extensions, max files)
SPEC = [
    ("ho-python-mindmeld",  "MindMeld",              "python",     (".py",),           22),
    # VENDORED upstream code (nghttp2 under duckdb-bigquery/spack-stage/.../vendor/). For a
    # holdout this is better material than first-party code, not worse: it is certainly in no
    # training corpus, and it is written in someone else's style. The vendor/test skips are
    # lifted for these two, which is why they carry allow_vendor.
    # First choice here was vendored rustdoc-js test data, which the engine could not parse at
    # all ("Catalog Error: Table with name fx_ho_js_nghttp2 does not exist") -- those files are
    # a rustdoc assertion DSL, not JavaScript. Real game code instead, small but genuine; the
    # JS family is mainly carried by ho-ts-cockpit anyway.
    ("ho-js-amongus",       "amongus-clone",         "javascript", (".js",),           12, True, 15),
    ("ho-go-nghttp2",       "duckdb-bigquery",       "go",         (".go",),           8, True),
    ("ho-ts-cockpit",       "cockpit-file-sharing",  "typescript", (".ts",),           20),
    ("ho-rust-fabric",      "cosmic-fabric",         "rust",       (".rs",),           9),
    ("ho-java-rdkit",       "rdkit",                 "java",       (".java",),         20),
    ("ho-c-graphqlparser",  "libgraphqlparser",      "c",          (".c", ".h"),       18),
    ("ho-cpp-nsjail",       "nsjail-python",         "cpp",        (".cc", ".cpp"),    14),
    ("ho-bash-plinking",    "plinking_duck",         "bash",       (".sh",),           18),
    ("ho-sql-iceberg",      "duckdb_iceberg",        "sql",        (".sql",),          20),
    ("ho-ruby-grit",        "grit",                  "ruby",       (".rb",),           20),
]
SKIP_DIRS = {".git", "node_modules", "build", "target", "__pycache__", ".venv", "venv",
             "dist", ".git-worktree", ".git-worktree-shared", "trees", ".emsdk", "test",
             "tests", "vendor", "third_party"}


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def pick(base, exts, cap, allow_vendor=False, lo=30):
    """Mid-sized files, deepest-first excluded: prefer real source over generated stubs."""
    found = []
    for dp, dns, fns in os.walk(base):
        skip = SKIP_DIRS - {"vendor", "third_party", "test", "tests"} if allow_vendor else SKIP_DIRS
        dns[:] = [d for d in dns if d not in skip and not d.startswith(".")]
        for fn in fns:
            if not fn.endswith(exts):
                continue
            p = os.path.join(dp, fn)
            try:
                n = sum(1 for _ in open(p, errors="ignore"))
            except OSError:
                continue
            if lo <= n <= 700:          # big enough to hold structure, small enough to bound
                found.append((n, os.path.relpath(p, base), p))
    found.sort(key=lambda t: -t[0])
    return found[:cap]


def main():
    manifest = {"fixtures": {}, "note": "HOLDOUT ONLY. Never add these to any training corpus."}
    for spec in SPEC:
        name, repo, lang, exts, cap = spec[:5]
        allow_vendor = len(spec) > 5 and spec[5]
        lo = spec[6] if len(spec) > 6 else 30
        rp = os.path.join(ROOT, repo)
        base = os.path.join(rp, "main") if os.path.isdir(os.path.join(rp, "main")) else rp
        if not os.path.isdir(base):
            print("%-22s MISSING %s" % (name, base)); continue
        files = pick(base, exts, cap, allow_vendor, lo)
        if not files:
            print("%-22s no files matched" % name); continue
        dest = os.path.join(OUT, name)
        shutil.rmtree(dest, ignore_errors=True)
        recs, total = [], 0
        for n, rel, src in files:
            dst = os.path.join(dest, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copy2(src, dst)
            recs.append({"path": rel, "source": rel, "lines": n,
                         "bytes": os.path.getsize(src), "sha256": sha256(src)})
            total += n
        commit = subprocess.run(["git", "-C", base, "rev-parse", "HEAD"],
                                capture_output=True, text=True).stdout.strip() or None
        manifest["fixtures"][name] = {"repo": repo, "language": lang,
                                      "commit": commit, "files": recs}
        print("%-22s %-11s %2d files %6d lines  repo=%s" % (name, lang, len(recs), total, repo))
    json.dump(manifest, open(os.path.join(OUT, "MANIFEST.json"), "w"), indent=1)
    print("\n%d fixtures -> %s" % (len(manifest["fixtures"]), OUT))


if __name__ == "__main__":
    main()
