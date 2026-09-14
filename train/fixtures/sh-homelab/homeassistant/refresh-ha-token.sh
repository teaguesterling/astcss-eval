#!/bin/bash
# refresh-ha-token — replace the homelab's stored HA long-lived token.
#
# Needed when HA's token starts returning 401 — most often after you change
# your HA password (HA revokes long-lived tokens on a password change). The
# token lives at ~/.config/homelab/ha-token and is read by the eero presence
# pusher + any homelab tooling that talks to HA. Run on dobby (HA is local).
#
#   bash ~/projects/homelab/homeassistant/refresh-ha-token.sh
set -euo pipefail
TOKEN_FILE="${HOMELAB_HA_TOKEN_FILE:-$HOME/.config/homelab/ha-token}"
HA="${HA_URL:-http://localhost:8123}"

cat <<EOF
Mint a fresh long-lived token in Home Assistant:
  1. Open $HA  (or http://dobby.lan:8123) and log in with your CURRENT password
  2. Click your name (bottom-left) -> Security tab
  3. Long-lived access tokens -> Create Token -> name it "homelab" -> OK
  4. Copy it (shown only once), then paste below (input is hidden).

EOF
read -rsp 'Paste HA token: ' TOK; echo
[ -n "${TOK:-}" ] || { echo "no token entered — aborted."; exit 1; }

# Verify BEFORE saving, so a bad paste never clobbers a working token.
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 8 \
        -H "Authorization: Bearer $TOK" "$HA/api/" || echo 000)
if [ "$code" != "200" ]; then
    echo "token REJECTED (HTTP $code) — not saved. Re-check you copied the whole token."
    exit 1
fi

mkdir -p "$(dirname "$TOKEN_FILE")"
( umask 077; printf '%s' "$TOK" > "$TOKEN_FILE" )
chmod 600 "$TOKEN_FILE"
echo "saved + verified -> $TOKEN_FILE (HTTP 200)"

# Revive the eero presence pusher (it reads the same token file).
EERO="$HOME/projects/homelab/eero/tool/.venv/bin/eero"
if [ -x "$EERO" ]; then
    echo "--- eero presence test ---"
    ( cd "$(dirname "$(dirname "$EERO")")" && "$EERO" presence push 2>&1 | head -3 ) || true
fi
echo "done."
