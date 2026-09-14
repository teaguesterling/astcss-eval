#!/bin/bash
# Non-destructive merge of opt-only projects into fast. Copies only; never deletes.
# opt copies stay put; deletion is a separate, later, gated pass.
set -uo pipefail
OPT=/srv/physical/opt/teague/Projects
FAST=/srv/physical/fast/home/teague/Projects
STAMP=$(date +%Y%m%d-%H%M%S)
LOG=/srv/physical/fast/home/teague/opt-merge-$STAMP.log
MAN=/srv/physical/fast/home/teague/opt-merge-manifest-$STAMP.tsv
RESCUE=$FAST/_opt-rescue-$STAMP

EXCLUDES=(--exclude=build/ --exclude=.venv/ --exclude=venv/ --exclude=node_modules/
          --exclude=dist/ --exclude=target/ --exclude='cmake-build-*/'
          --exclude=.spack-env/ --exclude=__pycache__/)

# Huge reconstructible toolchains/tutorials: leave on opt, but rescue unpushed commits.
LEAVE="spack spack~ spackos spack-testing llm-learning"
# Copy whole (git-LFS) — no build excludes so lfs-store comes along.
WHOLE="pajama-man"
# Non-project junk: skip.
SKIP="blarg.yaml blarg2.yaml metastore_db"

mkdir -p "$RESCUE"
printf "name\taction\tresult\tbytes\n" > "$MAN"
exec > >(tee -a "$LOG") 2>&1
echo "=== opt->fast non-destructive merge $STAMP ==="

mapfile -t INBOTH < <(comm -12 <(ls "$OPT"|sort) <(ls "$FAST" 2>/dev/null|sort))
is_inboth(){ local x; for x in "${INBOTH[@]}"; do [ "$x" = "$1" ] && return 0; done; return 1; }
in_list(){ local n="$1"; shift; local x; for x in "$@"; do [ "$x" = "$n" ] && return 0; done; return 1; }

for n in $(ls "$OPT"); do
  is_inboth "$n" && continue                      # fast is canonical for in-both; leave opt copy
  if in_list "$n" $SKIP; then
    echo "SKIP(junk)  $n"; printf "%s\tskip-junk\t-\t-\n" "$n" >>"$MAN"; continue; fi
  if in_list "$n" $LEAVE; then
    if [ -d "$OPT/$n/.git" ] && git -C "$OPT/$n" bundle create "$RESCUE/$n.bundle" --branches --not --remotes >/dev/null 2>&1; then
      echo "LEAVE+rescue $n"; printf "%s\tleave+bundle\tok\t-\n" "$n" >>"$MAN"
    else
      echo "LEAVE       $n (no unpushed / non-git)"; printf "%s\tleave\t-\t-\n" "$n" >>"$MAN"
    fi
    continue
  fi
  if in_list "$n" $WHOLE; then rsync -a "$OPT/$n/" "$FAST/$n/"; rc=$?
  else rsync -a "${EXCLUDES[@]}" "$OPT/$n/" "$FAST/$n/"; rc=$?; fi
  if [ $rc -eq 0 ] && [ -d "$FAST/$n" ]; then
    b=$(du -sb "$FAST/$n" 2>/dev/null | cut -f1)
    echo "COPIED      $n ($((b/1024/1024)) MiB)"; printf "%s\tcopy\tok\t%s\n" "$n" "$b" >>"$MAN"
  else
    echo "FAILED      $n rc=$rc"; printf "%s\tcopy\tFAIL(%s)\t-\n" "$n" "$rc" >>"$MAN"
  fi
done

# Reconcile opt-only uncommitted files for in-both repos that had real content.
recon(){ local repo="$1"; shift; local f src dst
  for f in "$@"; do src="$OPT/$repo/$f"; dst="$FAST/$repo/$f"
    [ -e "$src" ] || continue
    if [ ! -e "$dst" ]; then mkdir -p "$(dirname "$dst")"; cp -a "$src" "$dst"
      echo "RECON copy-in  $repo/$f"; printf "%s\trecon-copyin\tok\t-\n" "$repo/$f" >>"$MAN"
    elif diff -rq "$src" "$dst" >/dev/null 2>&1; then
      echo "RECON same     $repo/$f"; printf "%s\trecon-same\t-\t-\n" "$repo/$f" >>"$MAN"
    else cp -a "$src" "$dst.from-opt-$STAMP"
      echo "RECON sidecar  $repo/$f (.from-opt-$STAMP)"; printf "%s\trecon-sidecar\tdiffer\t-\n" "$repo/$f" >>"$MAN"
    fi
  done; }
recon squackit pyproject.toml scripts/find-code.py scripts/sql_eval.py scripts/selector_eval.py scripts/staged_dsl_demo.py
recon judgementalmonad.com LICENSE _templates blog/fuel/11-sandbox-specs.md experiments/tools/run-remaining.sh \
      docs/superpowers/plans/2026-04-02-blog-restructure.md docs/superpowers/specs/2026-04-02-blog-restructure-design.md

echo "=== DONE  manifest:$MAN  rescue:$RESCUE ==="