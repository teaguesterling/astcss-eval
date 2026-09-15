#!/usr/bin/env bash
# Syncthing — Quadlet unit + Caddy site + /srv data dirs.
#
# Idempotent. Run ON dobby:  sudo bash syncthing/install.sh
#
# Prereqs (validated; aborts with a pointer if missing):
#   - /etc/containers/systemd exists       (Podman with Quadlet support)
#   - /etc/caddy/sites.d exists            (caddy/ deployed)
#   - subuid/subgid mappings configured    (for linuxserver PUID=1000)
#
# Vault note: this container mounts /srv/physical/apps/obsidian/vault as the
# shared vault. The dir is created on-demand if missing so syncthing can be
# deployed before obsidian; the obsidian installer will reuse the same dir.
#
# After this completes:
#   https://syncthing.dobby.lan  (CA trust per caddy/README.md). Pair other
#   devices via dobby's device ID, then share the `vault` folder.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "run with sudo" >&2; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"

OWNER=teague
GROUP=teague
SRV=/srv/physical/apps/syncthing
VAULT=/srv/physical/apps/obsidian/vault
QUADLET=/etc/containers/systemd/syncthing.container
SITE=/etc/caddy/sites.d/syncthing.caddy

# ── prereqs ──────────────────────────────────────────────────────────────────
for d in /etc/containers/systemd /etc/caddy/sites.d; do
  [ -d "$d" ] || { echo "missing: $d" >&2
    case "$d" in
      /etc/containers/systemd) echo "  -> install/upgrade podman (Quadlet)" >&2 ;;
      /etc/caddy/sites.d)     echo "  -> deploy caddy first (see ../caddy/)" >&2 ;;
    esac; exit 2; }
done
id -u "$OWNER" >/dev/null 2>&1 || { echo "user '$OWNER' not found" >&2; exit 2; }

real_uid=$(id -u "$OWNER"); real_gid=$(id -g "$OWNER")
if [ "$real_uid" != 1000 ] || [ "$real_gid" != 1000 ]; then
  echo "WARN: $OWNER is uid=$real_uid gid=$real_gid but syncthing.container hardcodes PUID=PGID=1000" >&2
fi

# ── /srv data dirs ───────────────────────────────────────────────────────────
echo "== /srv data dirs =="
install -d -m 0755 /srv/physical 2>/dev/null || true
install -d -m 0755 /srv/physical/apps 2>/dev/null || true
install -d -m 0755 /srv/physical/apps/obsidian 2>/dev/null || true
install -d -o "$OWNER" -g "$GROUP" -m 0755 "$SRV/config" "$VAULT"
echo "  $SRV/config ready"
echo "  $VAULT ready (shared with obsidian container)"

# ── Quadlet unit ─────────────────────────────────────────────────────────────
echo "== quadlet =="
install -D -m 0644 "$HERE/syncthing.container" "$QUADLET"
echo "  $QUADLET"

# ── Caddy site ───────────────────────────────────────────────────────────────
echo "== caddy site =="
install -D -m 0644 "$HERE/syncthing.caddy" "$SITE"
echo "  $SITE"

# ── start / restart ──────────────────────────────────────────────────────────
echo "== systemd daemon-reload =="
systemctl daemon-reload

echo "== syncthing =="
if systemctl is-active --quiet syncthing; then
  echo "  already active — restarting to pick up unit changes"
  systemctl restart syncthing
else
  systemctl start syncthing
fi

echo "== caddy reload =="
if systemctl is-active --quiet caddy; then
  systemctl reload caddy
  echo "  caddy reloaded — picked up the new site"
else
  echo "  caddy not running — start it to pick up the new site"
fi

echo
echo "Done."
echo "  status: sudo systemctl status syncthing"
echo "  logs:   sudo journalctl -u syncthing -f"
echo "  reach:  https://syncthing.dobby.lan"
echo "  next:   open the web UI, copy this peer's device ID, share with other"
echo "          devices, then add the 'vault' folder (Send & Receive)."
