#!/bin/bash
# sleep-displays.sh — disable every output the cosmic compositor knows
# about. Companion to wake-displays.sh.
#
# WARNING: disables ALL outputs, including the primary. You won't be able
# to interact with the lock screen until something re-enables an output
# (`wake-displays.sh`, `loginctl unlock-session` if cosmic-display-control
# is running, or ssh in and re-enable manually).
#
# For the everyday "lock screen + auto-disable secondaries" workflow, just
# `loginctl lock-session` instead — the cosmic-display-control applet
# handles the disable, leaving the primary up for unlocking.

set -uo pipefail

if ! command -v cosmic-randr >/dev/null 2>&1; then
    echo "sleep-displays: cosmic-randr not found in PATH" >&2
    exit 1
fi

mapfile -t OUTPUTS < <(
    cosmic-randr list --kdl 2>/dev/null \
        | grep -oP '^output\s+"\K[^"]+'
)

if [[ ${#OUTPUTS[@]} -eq 0 ]]; then
    echo "sleep-displays: no outputs found (is the compositor running?)" >&2
    exit 1
fi

rc=0
for out in "${OUTPUTS[@]}"; do
    if ! cosmic-randr disable "$out" 2>/dev/null; then
        echo "sleep-displays: failed to disable $out" >&2
        rc=1
    fi
done

exit "$rc"
