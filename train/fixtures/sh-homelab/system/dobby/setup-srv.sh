#!/usr/bin/env bash
# dobby Phase 1 of the /srv reorg (see docs/storage-layout.md + the reorg spec).
# Promotes the staged family/shared data into the /srv convention:
#   /srv/physical/{family,shared}   <- canonical bytes (instant same-fs move from ~)
#   /srv/logical/{family,shared}    <- bind mounts; what Samba/consumers address
# Idempotent. Run ON dobby:  sudo bash system/dobby/setup-srv.sh
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "run with sudo" >&2; exit 1; }
getent group plex >/dev/null || { echo "ERROR: 'plex' group missing" >&2; exit 1; }

STAGE=/home/teague/incoming-shared

# --- Guard: refuse to run while the staging copy is still in flight ----------
if pgrep -x rsync >/dev/null 2>&1; then
  echo "ERROR: rsync still running -- staging not finished. Wait for it." >&2; exit 1
fi
if [ -d "$STAGE" ] && ! grep -q '=== DONE' /home/teague/stage-shared.log 2>/dev/null \
   && [ ! -e /srv/physical/family ]; then
  echo "ERROR: staging log has no 'DONE' marker and /srv not set up yet." >&2
  echo "       Confirm $STAGE is complete before promoting." >&2; exit 1
fi

mkdir -p /srv/physical /srv/logical

# --- Promote staged data -> /srv/physical (instant rename; same root fs) ------
for pool in family shared; do
  if [ -e "/srv/physical/$pool" ]; then
    echo "/srv/physical/$pool already present -- skip move"
  elif [ -d "$STAGE/$pool" ]; then
    echo "moving $STAGE/$pool -> /srv/physical/$pool"
    mv "$STAGE/$pool" "/srv/physical/$pool"
  else
    echo "WARN: neither /srv/physical/$pool nor $STAGE/$pool exists" >&2
  fi
done

chown -R teague:plex /srv/physical/family /srv/physical/shared 2>/dev/null || true
chmod 2775 /srv/physical /srv/physical/family /srv/physical/shared 2>/dev/null || true

# --- Logical layer: bind physical -> logical, persisted in fstab --------------
add_bind() {  # $1 = pool
  local src="/srv/physical/$1" dst="/srv/logical/$1"
  mkdir -p "$dst"
  if ! grep -qE "[[:space:]]${dst}[[:space:]]" /etc/fstab; then
    printf '%s\t%s\tnone\tbind\t0 0\n' "$src" "$dst" >> /etc/fstab
    echo "fstab += bind  $src -> $dst"
  fi
  mountpoint -q "$dst" || mount --bind "$src" "$dst"
}
add_bind family
add_bind shared

echo
echo "== layout =="
findmnt -R /srv 2>/dev/null || { ls -la /srv/physical; ls -la /srv/logical; }
echo
echo "Next: configure Samba to export /srv/logical/{family,shared} (system/dobby/samba/),"
echo "running in PARALLEL with the Buffalo. Do NOT cut clients over until backups are live."
