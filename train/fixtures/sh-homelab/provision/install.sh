#!/usr/bin/env bash
# install.sh — provision a host from its collection map.
#
#   ./install.sh                 # preview/install for $(hostname)
#   ./install.sh dobby           # target a specific host's map
#   DRY_RUN=1 ./install.sh       # just print what would be installed
#   sudo ./install.sh            # actually apt-install (flatpaks run as you)
#
# Collections live in collections/<name>.list (apt) and <name>.flatpak
# (flatpak app IDs). Each hosts/<host>.collections lists the collection
# names to apply. apt packages need root; flatpaks install --user as the
# invoking user.

set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
HOST="${1:-$(hostname)}"
MAP="$DIR/hosts/$HOST.collections"

[ -f "$MAP" ] || { echo "No collection map for host '$HOST' ($MAP)"; exit 1; }

colls="$(grep -vE '^\s*(#|$)' "$MAP")"
gather() { # $1 = extension (list|flatpak)
  local c f
  for c in $colls; do
    f="$DIR/collections/$c.$1"
    if [ -f "$f" ]; then
      grep -vE '^\s*(#|$)' "$f" || true
    fi
  done | sort -u
}
apt_pkgs="$(gather list)"
flatpaks="$(gather flatpak)"

echo "Host: $HOST"
echo "Collections: $(echo $colls)"
echo "apt packages ($(echo "$apt_pkgs" | grep -c .)): $(echo $apt_pkgs)"
echo "flatpaks ($(echo "$flatpaks" | grep -c .)): $(echo $flatpaks)"
echo

[ "${DRY_RUN:-}" = 1 ] && { echo "(dry run — nothing installed)"; exit 0; }

if [ -n "$apt_pkgs" ]; then
  if [ "$(id -u)" -ne 0 ]; then
    echo "apt install needs root. Re-run with sudo (or DRY_RUN=1 to preview)." >&2
    exit 1
  fi
  apt-get update
  # shellcheck disable=SC2086
  apt-get install -y $apt_pkgs
fi

if [ -n "$flatpaks" ] && command -v flatpak >/dev/null 2>&1; then
  runuser="${SUDO_USER:-$USER}"
  # shellcheck disable=SC2086
  sudo -u "$runuser" flatpak install --user -y flathub $flatpaks || true
fi

# Run a command as the invoking (non-root) user, even when install.sh is sudo'd.
run_user() { if [ "$(id -u)" -eq 0 ]; then sudo -u "${SUDO_USER:-root}" -H "$@"; else "$@"; fi; }

# --- non-apt tools (.tools manifests: name<TAB>method<TAB>spec) ---
for c in $colls; do
  tf="$DIR/collections/$c.tools"
  [ -f "$tf" ] || continue
  while IFS=$'\t' read -r name method spec; do
    case "$name" in ''|\#*) continue ;; esac
    echo "[tool] $name ($method)"
    case "$method" in
      npm)    run_user npm install -g "$spec"            || echo "  ! npm failed (check npm global prefix)" ;;
      pipx)   run_user pipx install "$spec"              || echo "  ! pipx failed" ;;
      script) run_user sh -c "curl -fsSL '$spec' | sh"   || echo "  ! install script failed" ;;
      *)      echo "  ! unknown method: $method" ;;
    esac
  done < "$tf"
done

# --- duckdb extensions (when the duckdb collection is active) ---
if printf '%s\n' $colls | grep -qx duckdb; then
  extf="$DIR/collections/duckdb-extensions.txt"
  user="${SUDO_USER:-$USER}"
  duckdb_bin="$(run_user bash -lc 'command -v duckdb' 2>/dev/null || true)"
  [ -n "$duckdb_bin" ] || duckdb_bin="$(eval echo "~$user")/.bin/duckdb"
  if [ -f "$extf" ] && run_user test -x "$duckdb_bin"; then
    echo "[duckdb] installing extensions from $(basename "$extf")"
    sql=""
    while read -r name src; do
      case "$name" in ''|\#*) continue ;; esac
      if [ "$src" = community ]; then sql="$sql INSTALL $name FROM community;"
      else sql="$sql INSTALL $name;"; fi
    done < "$extf"
    run_user "$duckdb_bin" -c "$sql" || echo "  ! some extensions failed to install"
  else
    echo "[duckdb] skipping extensions (duckdb binary or manifest not found)"
  fi
fi

echo "Done."
