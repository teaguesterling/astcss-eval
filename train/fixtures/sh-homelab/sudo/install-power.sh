#!/bin/sh
# install-power.sh — grant NOPASSWD for clean power control.
#
# After install, these run without a password prompt:
#   sudo systemctl reboot
#   sudo systemctl poweroff
#   sudo systemctl suspend
#
# Exact-command sudoers entries (no wrapper needed): sudoers matches the
# full command + args, so `systemctl reboot` is allowed but
# `systemctl reboot --force` or any other systemctl verb is not.
#
# Run as:
#   sudo sh sudo/install-power.sh
#
# Idempotent — safe to re-run.

set -e

if [ "$(id -u)" -ne 0 ]; then
    echo "must be root; run with: sudo sh $0" >&2
    exit 1
fi

USER_NAME="${SUDO_USER:-teague}"

SYSTEMCTL="$(command -v systemctl)"
[ -n "$SYSTEMCTL" ] || { echo "systemctl not found" >&2; exit 1; }

cat > /etc/sudoers.d/power <<EOF
$USER_NAME ALL=(root) NOPASSWD: $SYSTEMCTL reboot, $SYSTEMCTL poweroff, $SYSTEMCTL suspend
EOF
chmod 0440 /etc/sudoers.d/power

# Validate the sudoers fragment before declaring victory.
visudo -c -q

echo "installed /etc/sudoers.d/power (NOPASSWD for $USER_NAME)"
echo "now: 'sudo systemctl {reboot,poweroff,suspend}' run without a password."
