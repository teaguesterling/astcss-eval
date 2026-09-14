#!/usr/bin/env bash
# Samba infra for dobby: export the /srv/logical views (replaces the Buffalo NAS).
# Installs samba, wires homelab-shares.conf into smb.conf, validates, starts smbd.
#
# Does NOT create users/passwords -- that's yours, when it's time:
#     sudo smbpasswd -a <user>          # set SMB password
#     sudo usermod  -aG plex <user>     # grant access to the shares
#
# Idempotent. Run ON dobby:  sudo bash system/dobby/samba/install-samba.sh
# (Run setup-srv.sh first so /srv/logical/{family,shared} exist.)
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "run with sudo" >&2; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"
SMB=/etc/samba/smb.conf

if ! command -v smbd >/dev/null 2>&1; then
  echo "installing samba..."
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y samba
fi

install -D -m 0644 "$HERE/homelab-shares.conf" /etc/samba/homelab-shares.conf

# Wire the include into [global] (idempotent; back up smb.conf once).
cp -n "$SMB" "$SMB.homelab-bak" 2>/dev/null || true
if ! grep -qF 'include = /etc/samba/homelab-shares.conf' "$SMB"; then
  awk 'BEGIN{ins=0} {print}
       /^\[global\]/ && !ins {print "   include = /etc/samba/homelab-shares.conf"; ins=1}' \
      "$SMB" > "$SMB.new"
  mv "$SMB.new" "$SMB"
  echo "wired include into [global]"
fi

echo "== testparm (config validation) =="
testparm -s >/dev/null && echo "  config OK"

systemctl enable --now smbd
systemctl restart smbd

echo
echo "Samba running. Defined shares:"
testparm -s 2>/dev/null | grep -E '^\[' || true
echo
echo "Reminder: /srv/logical/{family,shared} must exist (run setup-srv.sh first),"
echo "and create users when it's time:  sudo smbpasswd -a <user> ; sudo usermod -aG plex <user>"
