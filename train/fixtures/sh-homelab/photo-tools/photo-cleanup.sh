#!/usr/bin/env bash
# ============================================================================
# photo-cleanup.sh — spring-cleaning artifact for the photo-dedup work.
# THIS SCRIPT IS REVIEW-ONLY BY DESIGN. Two safety locks:
#   1. Every actionable `do_rm` is COMMENTED OUT — uncomment what you want.
#   2. RUN=1 must also be set to actually delete (defaults to dry-run).
# A fresh `bash ~/photo-cleanup.sh` (or even `RUN=1 bash …`) is a NO-OP until
# you deliberately uncomment a section.
#
# STATUS tags per section:
#   READY            = verification done; uncomment + RUN=1 to delete.
#   NOT CONFIRMED    = pending an analysis step; do not uncomment yet.
#   QUARANTINE-MOVE  = will be a reversible move-list, not rm; placeholder.
#   REVIEW-BY-HAND   = never automate; eyeball + manual action.
#
# Generated 2026-05-29 from
#   ~/Projects/homelab/docs/specs/2026-05-29-photo-dedup-scope.md
#
# Paths RECONCILED 2026-06-03 to the landed layout (pool rename): /mnt/fast →
# /srv/logical/workspace, /mnt/bulk → /srv/logical/archive. §1a/§2a verified on
# disk: the deletable 2026 duplicate is on workspace; the canonical copy survives
# at /srv/logical/archive/home/teague/Downloads/ (all 5 chunks present), so §1a is
# a duplicate-removal, not a last-copy delete. Both safety locks remain engaged.
# See docs/plans/2026-06-03-data-cleanup-dedup-readiness.md.
# ============================================================================

set -u
RUN="${RUN:-0}"

do_rm() {
  for f in "$@"; do
    if [ "$RUN" = 1 ]; then
      if [ -e "$f" ]; then rm -v -- "$f"; else echo "  (already gone) $f"; fi
    else
      if [ -e "$f" ]; then printf '  WOULD rm: %s\n' "$f"
      else                  printf '  (skip; not present) %s\n' "$f"; fi
    fi
  done
}
banner() { echo; echo "==[ $* ]=="; }

if [ "$RUN" = 1 ]; then
  echo "*** RUN=1 set — but every section is still commented out. No-op until you uncomment. ***"
else
  echo "*** DRY-RUN — both safety locks engaged. ***"
fi


# ============================================================================
# 1a. STATUS: READY — 2026 Takeout duplicated tarballs on /srv/logical/workspace (~241 GB)
# ============================================================================
# What:  the 5 chunks of the 2026-05-18 Google Photos Takeout *copy* on
#        /srv/logical/workspace — duplicated from /srv/logical/archive/home/teague/Downloads/, which we
#        keep as the permanent copy (workflow: fast = scratch, bulk = storage).
# Why safe (evidence in /home/teague/takeout-cmp.log):
#   • Full cmp(1) byte-compare of all 5 pairs ran 2026-05-29; ALL 5 IDENTICAL.
#   • Same sizes, same mtimes (to the nanosecond), first-MB sha256 matched.
#   • The extracted analysis tree /srv/logical/workspace/home/teague/takeout-extract/ is a
#     SEPARATE directory and is NOT touched here.
# Reclaim: ~241 GB freed on /srv/logical/workspace.
# Enable: uncomment the `banner` + `do_rm` lines below, then RUN=1.
#
# banner "1a. READY — 2026 Takeout duplicates on /srv/logical/workspace (~241 GB)"
# do_rm /srv/logical/workspace/home/teague/takeout-20260518T030424Z-3-001.tgz \
#       /srv/logical/workspace/home/teague/takeout-20260518T030424Z-3-002.tgz \
#       /srv/logical/workspace/home/teague/takeout-20260518T030424Z-3-003.tgz \
#       /srv/logical/workspace/home/teague/takeout-20260518T030424Z-3-004.tgz \
#       /srv/logical/workspace/home/teague/takeout-20260518T030424Z-3-005.tgz


# ============================================================================
# 2a. STATUS: READY — 2023 Takeout tarballs (~169 GB)
# ============================================================================
# What:  4 chunks of the 2023-11-24 Takeout in
#        /srv/logical/archive/home/sterling/Pictures/From Google 2023/.
# Why safe (evidence in /srv/logical/workspace/home/teague/takeout-extract/photos.duckdb,
# tables tk23 vs tk):
#   • 2023: 38,799 media files → 33,778 distinct (name+size).
#   • 33,480 of those 33,778 are ALSO in 2026 — 99.1% strict match.
#   • Only 84 filenames in 2023 don't appear in 2026 at all (0.2%).
#   • The 298 "strict-unique-to-2023" files = just 0.45 GB total, and the
#     sample shows them to be re-encoded/edited copies (e.g. `…-edited.jpg`,
#     `…(1).jpg`) that exist in 2026 with slightly different bytes — not
#     genuinely lost content.
#   • Net: 2023 ⊆ 2026 confirmed. The 169 GB of 2023 tarballs are redundant.
# Reclaim: ~169 GB on /srv/logical/archive.
# Enable: uncomment the `banner` + `do_rm` lines below, then RUN=1.
#
# banner "2a. READY — 2023 Takeout tarballs (~169 GB)"
# do_rm "/srv/logical/archive/home/sterling/Pictures/From Google 2023/takeout-20231124T203811Z-001.tgz" \
#       "/srv/logical/archive/home/sterling/Pictures/From Google 2023/takeout-20231124T203811Z-002.tgz" \
#       "/srv/logical/archive/home/sterling/Pictures/From Google 2023/takeout-20231124T203811Z-003.tgz" \
#       "/srv/logical/archive/home/sterling/Pictures/From Google 2023/takeout-20231124T203811Z-004.tgz"


# ============================================================================
# 2b. STATUS: READY — Internal Takeout album-duplication (~27 GB)
# ============================================================================
# What: 6,388 redundant copies of the same photo across multiple Google albums.
#       Manifest at /srv/logical/workspace/home/teague/takeout-extract/manifest-album-dup.tsv
#       with 5,021 'keep' rows (canonical pick = non-year-bucket album
#       preferred, then shortest path) and 6,388 'move' rows. Uses the
#       reversible mover ~/quarantine-move.sh (preserves relative paths under
#       the quarantine dir, so reversal = mirror-mv back).
# Effect: ~26.9 GB moved from takeout-extract → /srv/logical/workspace/quarantine/album-dup/.
# Enable: uncomment the lines below, then RUN=1.
#
# banner "2b. READY — Album-dup quarantine (~27 GB)"
# RUN=1 bash ~/quarantine-move.sh \
#   /srv/logical/workspace/home/teague/takeout-extract/manifest-album-dup.tsv \
#   /srv/logical/workspace/quarantine/album-dup move


# ============================================================================
# 2c. STATUS: READY — "Worthless" candidates (~2.6 GB, refined post-vision-review)
# ============================================================================
# What: ~7,564 files matching filename/size heuristics. Manifest at
#       /srv/logical/workspace/home/teague/takeout-extract/manifest-worthless.tsv
#       (ABSOLUTE paths). Each row tagged with a 'reason' column:
#         screenshot:  ~3,372 / 1,778 MB
#         messaging:   ~2,979 /   798 MB   (WhatsApp/Signal patterns)
#         tiny <100KB: ~1,213 /    73 MB
# Vision-review findings (Claude vision, 2026-05-29):
#   • DROPPED `meme_ext` (.gif): samples were `…-ANIMATION.gif` /
#     `…-MOTION.gif` = Google Motion Photos (Live Photos from your phone), not
#     memes/web-grabs. Keepers.
#   • screenshot + messaging confirmed clean.
#   • tiny is a mix; one sampled `IMG_…84KB.jpg` turned out to be a Pokémon GO
#     screenshot in the `Archive` album — still useful to set aside.
# Effect: ~2.6 GB moved to /srv/logical/workspace/quarantine/worthless/.
# Enable: uncomment + RUN=1.
#
# banner "2c. READY — Worthless quarantine (~2.6 GB, refined)"
# RUN=1 bash ~/quarantine-move.sh \
#   /srv/logical/workspace/home/teague/takeout-extract/manifest-worthless.tsv \
#   /srv/logical/workspace/quarantine/worthless


# ============================================================================
# 2d. STATUS: NOT CONFIRMED — Stray archive dupes on NAS shared/Downloads (~5 GB)
# ============================================================================
# Reachable via dobby's CIFS mount; decide each by hand (CIFS deletes are slow,
# best done from dobby):
#   /mnt/cifs/nas/shared/Downloads/{ISOs,System,System/SteamOS}/SteamOSInstaller.zip   (×3)
#   /mnt/cifs/nas/shared/Pictures/{teague/baby,From Pinky/Baby Bump!}/Adrienne + Bump.zip
#       + /mnt/cifs/nas/family/Pictures/From Pinky/Baby Bump!/Adrienne + Bump.zip       (×3)
#   /mnt/cifs/nas/shared/Downloads/Software/CS2/{,Packages/}VCS2.zip                   (×2)
#   /mnt/cifs/nas/shared/Downloads/Software/MatLab-R2009b.tar.gz                       (4.4 GB, ancient)


# ============================================================================
# 2e. STATUS: NEEDS REFINEMENT — "Silly / no-GPS" pile (DEFERRED)
# ============================================================================
# Hypothesis: no-GPS = potentially silly; organize to a side dir for laughs.
# Reality (sampling 2026-05-29 killed the hypothesis): no-GPS is too broad.
# The 24,084 files / ~54 GB pile includes lots of REAL KEEPERS:
#   • DSLR photos (_DSC*, Sterling*) — DSLRs don't tag GPS by default.
#   • 3,161 MP4 videos (~23 GB) — videos rarely tag GPS regardless of subject.
#   • Edited photos (-edited.jpg) — Google strips GPS on edit.
#   • Vacation photos in named albums (Ireland, Weekend in Portland, Safari West).
#   • Older phone photos (2013–2015 pre-GPS-always-on).
#
# A "weird-name in year-bucket" refinement (filename doesn't match phone
# patterns AND not DSLR/edited/MP4) lands at ~4,848 files / ~2.9 GB, BUT
# sampling showed it (a) largely overlaps with 2c (screenshots dominate), and
# (b) false-positives real photos like `Adrienne+TeagueWedding-320.jpg`.
#
# DO NOT enable. Decide a tighter signal first; meanwhile 2c picks up the
# obvious junk. The pHash near-dupe finder in section 4 may help surface
# additional candidates via visual similarity.
# (The manifest-silly.tsv has been removed — was too broad to be useful.)


# ============================================================================
# 3. STATUS: REVIEW-BY-HAND — never auto-delete (kept here as a checklist)
# ============================================================================
#   • /srv/logical/workspace/home/teague/takeout-extract/  — the EXTRACTED 2026 Takeout
#     (~244 GB). Used as the analysis source. Remove only AFTER the keep-set
#     is migrated to /srv/logical/archive per the fast=scratch workflow.
#   • /srv/logical/archive/home/teague/Downloads/takeout-20260518…tgz  — the permanent
#     2026 tarballs. Decide whether to keep them after the canonical photo
#     library is established (cold-storage redundancy vs. reclaim).
#   • /srv/logical/archive/home/sterling/Pictures/From Google 2023/  — anything beyond
#     the 4 .tgz files in 2a; eyeball the dir before doing anything.


# ============================================================================
# 4. TOOLS — separate scripts (not auto-run by this cleanup script)
# ============================================================================
# ~/quarantine-move.sh
#   The reversible mover used by 2b/2c above. Reads a manifest TSV with a
#   'source' column (and optional 'role' filter), moves matching files to a
#   target dir preserving relative paths. Dry-run by default; RUN=1 to act.
#
# ~/find-similar-photos.py
#   Perceptual-hash (pHash) near-duplicate finder. Catches what name+size
#   misses: re-encoded copies, slight crops/edits, burst-frame siblings.
#   Setup (once):
#     python3 -m pip install --user pillow imagehash duckdb
#   Run (index + query):
#     python3 ~/find-similar-photos.py index /srv/logical/workspace/home/teague/takeout-extract
#     python3 ~/find-similar-photos.py groups --max-distance 6 --limit 100
#   Output: groups of visually-similar images (path + size). Hand-review,
#   pick the canonical, then either rm or move the rest.


echo
if [ "$RUN" = 1 ]; then echo "RUN=1 set, but everything was commented out → no rm ran."
else echo "Dry-run complete. To act: uncomment a section AND set RUN=1."; fi
