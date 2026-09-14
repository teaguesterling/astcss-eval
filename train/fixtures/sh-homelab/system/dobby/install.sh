#!/usr/bin/env bash
# Deploy dobby system config (grub cmdline drop-in + fstab review). Idempotent.
# Run ON dobby:  sudo bash system/dobby/install.sh
#
# - Installs the grub.d cmdline drop-in (authoritative) + regenerates grub.cfg.
#   New cmdline (incl. the queued HDMI experiment) takes effect on the next REBOOT.
# - Shows the fstab diff for manual review/apply (never auto-clobbers /etc/fstab).
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "run with sudo" >&2; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"

echo "== grub cmdline drop-in =="
install -D -m 0644 "$HERE/grub.d/99-homelab.cfg" /etc/default/grub.d/99-homelab.cfg
# Make the drop-in the single source of truth: blank the base GRUB_CMDLINE_LINUX (back up first).
if grep -qE '^GRUB_CMDLINE_LINUX=' /etc/default/grub; then
  cp -n /etc/default/grub /etc/default/grub.homelab-bak || true
  sed -i 's#^GRUB_CMDLINE_LINUX=.*#GRUB_CMDLINE_LINUX=""  # set by /etc/default/grub.d/99-homelab.cfg#' /etc/default/grub
fi
update-grub
echo "  -> /etc/default/grub.d/99-homelab.cfg installed; grub.cfg regenerated."
echo "  -> new kernel cmdline (incl HDMI experiment) applies on next REBOOT."

echo
echo "== fstab (review + apply manually — NOT auto-replaced) =="
if diff -q /etc/fstab "$HERE/fstab" >/dev/null 2>&1; then
  echo "  /etc/fstab already matches repo."
else
  diff -u /etc/fstab "$HERE/fstab" || true
  echo "  -> review the diff, then: sudo cp '$HERE/fstab' /etc/fstab && sudo systemctl daemon-reload"
fi

echo
echo "Done. Apply the cmdline (+ run the HDMI experiment) with:  sudo reboot"
