#!/bin/bash
# Gated cleanup of redundant copies left behind by the 2026-05-31 opt->fast merge,
# plus the snape SteamLibrary (after it's been copied to longbottom opt/steam).
#
#   DRY-RUN by default — prints what it WOULD delete + reclaimable space.
#   Pass --apply to actually delete. Every item is re-verified live at run time;
#   anything that fails a safety gate is reported as REVIEW and never touched.
#
# Safety invariants (advisor-flagged):
#   - never delete an opt copy unless a complete copy exists on fast
#   - never delete a git repo whose commits/branches aren't all present on fast
#   - skip symlinks; skip anything dirty with non-tooling changes
#   - SteamLibrary on snape only after longbottom file-list MATCHES
set -uo pipefail
APPLY=0; [ "${1:-}" = "--apply" ] && APPLY=1
# Paths address the LOGICAL views (post 2026-06-03 pool rename): opt = longbottom-nvme2,
# workspace = longbottom-nvme0. NOTE: correcting these from the old /srv/physical/{opt,fast}
# (now empty stale mountpoints) ARMS this script — it was a guaranteed no-op before. Still
# dry-run by default; --apply required. See docs/plans/2026-06-03-data-cleanup-dedup-readiness.md.
OPT=/srv/logical/opt/teague/Projects
FAST=/srv/logical/workspace/home/teague/Projects
del(){ if [ "$APPLY" = 1 ]; then rm -rf "$1"; echo "   DELETED  $1"; else echo "   would-delete  $1"; fi; }
reclaim=0; add(){ reclaim=$((reclaim + $(du -sb "$1" 2>/dev/null|cut -f1) )); }

# Pools/dirs that STAY on opt (no-backup but in use) — never cleanup:
KEEP_PROJ="spack spack~ spackos spack-testing llm-learning"   # reconstructible toolchains/tutorials
in_list(){ local n="$1"; shift; local x; for x in "$@"; do [ "$x" = "$n" ] && return 0; done; return 1; }

# Hand-audited safe to drop (2026-06-07 opt-cleanup audit). Each tripped the REVIEW
# gates (uncommitted-on-opt / no-fast-copy / fast-not-git), but byte-comparison vs the
# fast (workspace) copy showed every one is: work already mirrored identically to fast,
# OR opt stale-behind fast (squackit v0.4.2<0.5.0 88<101 commits; grit), OR opt-only
# noise (caches/venvs/.spack-env, derby scratch metastore_db, empty phoenix, a one-line
# kibitzer config toggle, trivial single files). duckdb-community-extensions: thin
# submodule-pointer meta-repo, reconstructible from upstream (user-confirmed). Listed
# here so --apply reclaims them; they bypass the fast/git gates because a human verified
# them, not the gate. (One-time post-merge cleanup — re-audit if opt sees new work.)
CONFIRMED_DROP="barely-amongjs beat-drift-monitor duckdb duckdb-community-extensions \
duckdb_extension_parser_tools duckdb_rdkit git-messe-af grit judgementalmonad.com \
kibitzer libgraphqlparser metastore_db nsjail-python onthespot pacs pages phoenix \
semantic-workspace squackit"

echo "===== opt Projects redundant-copy cleanup ($([ $APPLY = 1 ] && echo APPLY || echo DRY-RUN)) ====="
for n in $(ls "$OPT" 2>/dev/null); do
  O="$OPT/$n"; F="$FAST/$n"
  [ -L "$O" ] && { echo "REVIEW  $n (symlink)"; continue; }
  [ -d "$O" ] || { echo "SKIP    $n (not a dir)"; continue; }
  in_list "$n" $KEEP_PROJ && { echo "KEEP    $n (toolchain, stays on opt)"; continue; }
  # hand-audited safe (2026-06-07) — bypass the fast/git gates below:
  in_list "$n" $CONFIRMED_DROP && { add "$O"; echo "DROP    $n (audited-safe 2026-06-07)"; del "$O"; continue; }
  # require a non-empty fast counterpart
  if [ ! -d "$F" ] || [ -z "$(ls -A "$F" 2>/dev/null)" ]; then echo "REVIEW  $n (no/empty fast copy)"; continue; fi
  # git safety: every opt local branch tip must be reachable on fast
  if [ -d "$O/.git" ]; then
    # real (non-tooling) uncommitted changes still only on opt?
    realdirty=$(git -C "$O" status --porcelain 2>/dev/null \
      | grep -vE '(\.lq/|\.mcp\.json|\.kibitzer/|\.lackpy/|\.fledgling)' | wc -l)
    [ "$realdirty" -gt 0 ] && { echo "REVIEW  $n ($realdirty real uncommitted on opt)"; continue; }
    if [ -d "$F/.git" ]; then
      unsafe=0
      for tip in $(git -C "$O" for-each-ref --format='%(objectname)' refs/heads refs/tags 2>/dev/null); do
        git -C "$F" merge-base --is-ancestor "$tip" \
          $(git -C "$F" for-each-ref --format='%(objectname)' refs/heads 2>/dev/null) 2>/dev/null \
          || { git -C "$F" cat-file -e "$tip" 2>/dev/null || unsafe=1; }
      done
      [ "$unsafe" = 1 ] && { echo "REVIEW  $n (opt has commits not on fast)"; continue; }
    else echo "REVIEW  $n (fast copy is not git)"; continue; fi
  fi
  add "$O"; echo "DELETE  $n"; del "$O"
done

echo; echo "===== disposable on opt ====="
T="$OPT/../Trash"
[ -d "$T" ] && { add "$T"; echo "DELETE  teague/Trash (disposable)"; del "$T"; }
# Stash dobby disk images: NOT reconstructible -> always REVIEW (user decides keep/move/drop)
echo "REVIEW  teague/Stash/dobbie-sda*.img + plex.img (~6.9G, NOT reconstructible; move to bulk if wanted)"

echo; echo "===== snape SteamLibrary (only after copy to longbottom verified) ====="
DEST=/srv/logical/opt/steam/SteamLibrary   # snape source stays /srv/physical/portable (rename to snape-nvme1 pending on snape)
if ssh -o ConnectTimeout=5 snape test -d /srv/physical/portable/SteamLibrary 2>/dev/null; then
  if [ -d "$DEST" ] && diff \
       <(ssh snape 'cd /srv/physical/portable/SteamLibrary && find . -type f|sort') \
       <(cd "$DEST" && find . -type f|sort) >/dev/null 2>&1; then
    echo "DELETE  snape:/srv/physical/portable/SteamLibrary (verified == longbottom $DEST)"
    if [ "$APPLY" = 1 ]; then ssh snape rm -rf /srv/physical/portable/SteamLibrary; echo "   DELETED on snape"; else echo "   would-delete on snape"; fi
  else echo "REVIEW  snape SteamLibrary — longbottom copy missing or file lists differ; do NOT delete"; fi
else echo "SKIP    snape SteamLibrary (already gone / snape unreachable)"; fi

echo; printf "===== reclaimable on opt (this run): %s GiB =====\n" "$((reclaim/1024/1024/1024))"
[ "$APPLY" = 0 ] && echo "(dry-run — re-run with --apply to delete the DELETE items; REVIEW items are never auto-deleted)"
