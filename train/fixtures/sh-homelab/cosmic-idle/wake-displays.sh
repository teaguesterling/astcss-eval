#!/bin/bash
# wake-displays.sh — enable every output the cosmic compositor knows about.
#
# Mirrors how cosmic-display-control mutates outputs: list via `cosmic-randr
# list --kdl`, then call `cosmic-randr enable <name>` per output.
#
# Must run inside the user systemd manager's cgroup so WAYLAND_DISPLAY +
# XDG_RUNTIME_DIR are populated.

set -uo pipefail

if ! command -v cosmic-randr >/dev/null 2>&1; then
    echo "wake-displays: cosmic-randr not found in PATH" >&2
    exit 1
fi

# `cosmic-randr list --kdl` emits node lines like:
#   output "DP-1" {
#       enabled true
#       ...
#   }
# Extract the quoted name from every `output` line.
mapfile -t OUTPUTS < <(
    cosmic-randr list --kdl 2>/dev/null \
        | grep -oP '^output\s+"\K[^"]+'
)

if [[ ${#OUTPUTS[@]} -eq 0 ]]; then
    echo "wake-displays: no outputs found (is the compositor running?)" >&2
    exit 1
fi

rc=0
for out in "${OUTPUTS[@]}"; do
    if ! cosmic-randr enable "$out" 2>/dev/null; then
        echo "wake-displays: failed to enable $out" >&2
        rc=1
    fi
done

exit "$rc"
