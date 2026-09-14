#!/usr/bin/env bash
# ============================================================================
# quarantine-move.sh — reversible move of files listed in a manifest TSV.
#
# Usage:  bash ~/quarantine-move.sh <manifest.tsv> <quarantine_dir> [role_filter]
#         RUN=1 to actually move (default: dry-run).
#
# Manifest header must include a 'source' column. If a 'role' column exists
# and [role_filter] is given (e.g. "move"), only act on rows where role==filter.
#
# Files are moved under <quarantine_dir>/, preserving their path relative to
# /srv/logical/workspace/home/teague/takeout-extract/  — so reversing is a mirror-mv back.
# ============================================================================
set -u
M="${1:-}"; Q="${2:-}"; FILTER="${3:-}"
RUN="${RUN:-0}"
PREFIX=/srv/logical/workspace/home/teague/takeout-extract/

[ -f "$M" ] || { echo "manifest not found: ${M:-<missing arg>}" >&2; exit 1; }
[ -n "$Q" ] || { echo "usage: $0 <manifest.tsv> <quarantine_dir> [role_filter]" >&2; exit 1; }
mkdir -p "$Q"
LOG="$Q/move.log"; : > "$LOG"

# parse header → column index map
IFS=$'\t' read -ra hdr < "$M"
declare -A col
for i in "${!hdr[@]}"; do col[${hdr[i]}]=$i; done
[ -n "${col[source]:-}" ] || { echo "manifest missing 'source' column" >&2; exit 1; }

n_total=0; n_act=0; n_gone=0
while IFS=$'\t' read -r -a F; do
  [ "${#F[@]}" -gt 0 ] || continue
  if [ -n "$FILTER" ] && [ -n "${col[role]:-}" ]; then
    [ "${F[${col[role]}]}" = "$FILTER" ] || continue
  fi
  src="${F[${col[source]}]}"
  n_total=$((n_total+1))
  if [ ! -e "$src" ]; then
    echo "  (already gone) $src" >> "$LOG"
    n_gone=$((n_gone+1))
    continue
  fi
  rel="${src#$PREFIX}"
  dst="$Q/$rel"
  if [ "$RUN" = 1 ]; then
    mkdir -p "$(dirname "$dst")"
    if mv -- "$src" "$dst" 2>>"$LOG"; then n_act=$((n_act+1))
    else echo "  ERR mv $src -> $dst" >> "$LOG"; fi
  else
    echo "  WOULD mv: $src  ->  $dst" >> "$LOG"
    n_act=$((n_act+1))
  fi
done < <(tail -n +2 "$M")

verb=$([ "$RUN" = 1 ] && echo "moved" || echo "would-move")
echo "scanned: $n_total | $verb: $n_act | already-gone: $n_gone"
echo "log: $LOG"
[ "$RUN" = 1 ] || echo "(DRY-RUN — set RUN=1 to actually move)"
