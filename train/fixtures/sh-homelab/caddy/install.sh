#!/usr/bin/env bash
# Caddy reverse proxy — Quadlet unit + /etc/caddy config + /srv data dirs.
#
# Idempotent. Run ON the host where Caddy will publish (currently dobby):
#   sudo bash caddy/install.sh
#
# Prereqs (validated; aborts with a pointer if missing):
#   - /etc/containers/systemd exists       (Podman with Quadlet support)
#   - host owner user exists               (for the /srv data dirs)
#
# /srv/physical is created on-demand if missing — system/dobby/setup-srv.sh
# still owns the file-server pools (family, shared); this installer only
# touches /srv/physical/apps/caddy/.
#
# After this completes Caddy is up on :80/:443 with the local internal CA.
# Trust the root cert on each client (see README.md for the scp + update-ca
# commands). Per-service site snippets land in /etc/caddy/sites.d/ via each
# service's own installer.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "run with sudo" >&2; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"

OWNER=teague
GROUP=teague
SRV=/srv/physical/apps/caddy
QUADLET=/etc/containers/systemd/caddy.container

# ── prereqs ──────────────────────────────────────────────────────────────────
[ -d /etc/containers/systemd ] || {
  echo "missing: /etc/containers/systemd — install/upgrade podman (Quadlet)" >&2; exit 2; }
id -u "$OWNER" >/dev/null 2>&1 || { echo "user '$OWNER' not found" >&2; exit 2; }

# ── /etc/caddy (host config) ─────────────────────────────────────────────────
echo "== /etc/caddy =="
install -d -m 0755 /etc/caddy /etc/caddy/sites.d
install -D -m 0644 "$HERE/Caddyfile" /etc/caddy/Caddyfile
echo "  /etc/caddy/Caddyfile"
echo "  /etc/caddy/sites.d/  (service snippets land here)"

# ── /srv data dirs ───────────────────────────────────────────────────────────
echo "== /srv data dirs =="
install -d -m 0755 /srv/physical 2>/dev/null || true   # don't clobber existing perms
install -d -m 0755 /srv/physical/apps 2>/dev/null || true
install -d -o "$OWNER" -g "$GROUP" -m 0755 "$SRV/data" "$SRV/config" "$SRV/web"
echo "  $SRV/{data,config,web} ready"

# ── Quadlet unit ─────────────────────────────────────────────────────────────
echo "== quadlet =="
install -D -m 0644 "$HERE/caddy.container" "$QUADLET"
echo "  $QUADLET"

# ── start / restart ──────────────────────────────────────────────────────────
echo "== systemd daemon-reload =="
systemctl daemon-reload

echo "== caddy =="
if systemctl is-active --quiet caddy; then
  echo "  already active — restarting to pick up unit changes"
  systemctl restart caddy
else
  systemctl start caddy
fi

# Wait briefly for the container to settle (PKI init on first boot).
for _ in 1 2 3 4 5; do
  systemctl is-active --quiet caddy && break
  sleep 1
done

echo
echo "Done."
echo "  status: sudo systemctl status caddy"
echo "  logs:   sudo journalctl -u caddy -f"
echo "  CA:     $SRV/data/caddy/pki/authorities/local/root.crt"
echo "          (scp it to each client; trust per caddy/README.md)"
echo "  next:   deploy per-service installers — they'll drop snippets into"
echo "          /etc/caddy/sites.d/ and reload caddy themselves."
