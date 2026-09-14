#!/usr/bin/env bash
# ca.dobby.lan — self-serve CA cert + install instructions site.
#
# Idempotent. Run ON dobby:  sudo bash ca/install.sh
#
# Prereqs:
#   - caddy/install.sh has been (re)run so /srv/physical/apps/caddy/web/
#     exists (the /web bind mount Caddy sees the docroot through)
#   - /etc/caddy/sites.d exists
#   - qrencode + openssl (used to build the artifacts below)
#
# What it does:
#   1. drops index.html into /srv/physical/apps/caddy/web/ca/
#   2. copies the Caddy local root cert there as dobby-ca.crt
#   3. generates dobby-ca.mobileconfig (iOS Configuration Profile bundling
#      the CA as an auto-trusted root — saves the iOS "Certificate Trust
#      Settings" toggle that everyone misses)
#   4. generates qr.png pointing at http://192.168.4.22/ for sharing
#      (scan with another phone's camera to get to this page)
#   5. installs the ca.dobby.lan site snippet (both HTTPS hostname and
#      HTTP-on-IP bootstrap entry points)
#   6. reloads caddy
#
# No quadlet — Caddy serves the static page itself. Re-run anytime to
# refresh the cert + mobileconfig (e.g. if Caddy's local CA ever rotates).
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "run with sudo" >&2; exit 1; }
HERE="$(cd "$(dirname "$0")" && pwd)"

OWNER=teague
GROUP=teague
DOCROOT=/srv/physical/apps/caddy/web/ca
SRC_CRT=/srv/physical/apps/caddy/data/caddy/pki/authorities/local/root.crt
SITE=/etc/caddy/sites.d/ca.caddy
DOBBY_IP=192.168.4.22
BOOTSTRAP_URL="http://${DOBBY_IP}/"

# ── prereqs ──────────────────────────────────────────────────────────────────
[ -d /srv/physical/apps/caddy/web ] || {
  echo "missing: /srv/physical/apps/caddy/web — re-run caddy/install.sh first" >&2; exit 2; }
[ -d /etc/caddy/sites.d ] || {
  echo "missing: /etc/caddy/sites.d — deploy caddy first" >&2; exit 2; }
[ -f "$SRC_CRT" ] || {
  echo "missing: $SRC_CRT — caddy hasn't issued its local CA yet" >&2
  echo "  -> start caddy (sudo systemctl start caddy), then re-run this." >&2; exit 2; }
for cmd in openssl base64; do
  command -v "$cmd" >/dev/null 2>&1 || {
    echo "missing tool: $cmd — apt install $cmd" >&2; exit 2; }
done

# ── docroot ──────────────────────────────────────────────────────────────────
echo "== docroot =="
install -d -o "$OWNER" -g "$GROUP" -m 0755 "$DOCROOT"
install -m 0644 "$HERE/index.html" "$DOCROOT/index.html"
echo "  $DOCROOT/index.html"

# Raw CA cert in PEM (browsers, Linux/Windows trust stores)
install -m 0644 "$SRC_CRT" "$DOCROOT/dobby-ca.crt"
echo "  $DOCROOT/dobby-ca.crt (copy of $SRC_CRT)"

# ── iOS .mobileconfig ────────────────────────────────────────────────────────
# Bundles the CA cert as a `com.apple.security.root` payload. On iOS, tapping
# the .mobileconfig in Safari triggers the Profile install flow AND marks the
# root as auto-trusted — bypassing the universally-missed "Settings -> General
# -> About -> Certificate Trust Settings" toggle that plain .crt installs need.
echo "== iOS Configuration Profile =="
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
# Convert PEM -> DER -> base64 (Apple wants DER inside <data>)
openssl x509 -outform DER -in "$SRC_CRT" -out "$TMP/ca.der"
CERT_B64="$(base64 -w0 < "$TMP/ca.der")"

# Derive stable UUIDs from the cert fingerprint so re-runs don't churn them.
# (iOS uses the profile UUID to detect "already installed / updating".)
FP="$(openssl x509 -in "$SRC_CRT" -noout -fingerprint -sha256 | sed 's/.*=//' | tr -d ':' | tr 'A-F' 'a-f')"
fmt_uuid() {  # take 32 hex chars, format as 8-4-4-4-12
  printf '%s' "$1" | awk '{
    s=$0
    printf "%s-%s-%s-%s-%s", substr(s,1,8), substr(s,9,4), substr(s,13,4), substr(s,17,4), substr(s,21,12)
  }'
}
UUID_CERT_PAYLOAD="$(fmt_uuid "${FP:0:32}")"
UUID_PROFILE="$(fmt_uuid "${FP:32:32}")"
CERT_CN="$(openssl x509 -in "$SRC_CRT" -noout -subject | sed -E 's/.*CN ?= ?([^,]+).*/\1/' | sed 's/[[:space:]]*$//')"

cat > "$DOCROOT/dobby-ca.mobileconfig" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>PayloadDisplayName</key>      <string>dobby.lan local CA</string>
  <key>PayloadIdentifier</key>       <string>lan.dobby.ca.profile</string>
  <key>PayloadDescription</key>      <string>Trusts ${CERT_CN} so *.dobby.lan services load without warnings.</string>
  <key>PayloadOrganization</key>     <string>dobby.lan</string>
  <key>PayloadType</key>             <string>Configuration</string>
  <key>PayloadUUID</key>             <string>${UUID_PROFILE}</string>
  <key>PayloadVersion</key>          <integer>1</integer>
  <key>PayloadContent</key>
  <array>
    <dict>
      <key>PayloadType</key>             <string>com.apple.security.root</string>
      <key>PayloadIdentifier</key>       <string>lan.dobby.ca.payload</string>
      <key>PayloadUUID</key>             <string>${UUID_CERT_PAYLOAD}</string>
      <key>PayloadVersion</key>          <integer>1</integer>
      <key>PayloadDisplayName</key>      <string>${CERT_CN}</string>
      <key>PayloadDescription</key>      <string>Root CA for *.dobby.lan.</string>
      <key>PayloadCertificateFileName</key><string>dobby-ca.crt</string>
      <key>PayloadContent</key>
      <data>
${CERT_B64}
      </data>
    </dict>
  </array>
</dict>
</plist>
EOF
chown "$OWNER:$GROUP" "$DOCROOT/dobby-ca.mobileconfig"
chmod 0644 "$DOCROOT/dobby-ca.mobileconfig"
echo "  $DOCROOT/dobby-ca.mobileconfig"

# ── QR code ──────────────────────────────────────────────────────────────────
# Points at the bootstrap HTTP URL so a fresh device can land on this page
# without DNS or cert trust. Show the camera to it, follow the on-page steps.
if command -v qrencode >/dev/null 2>&1; then
  echo "== QR code =="
  qrencode -o "$DOCROOT/qr.png" -s 8 -m 2 -t PNG -- "$BOOTSTRAP_URL"
  chown "$OWNER:$GROUP" "$DOCROOT/qr.png"
  chmod 0644 "$DOCROOT/qr.png"
  echo "  $DOCROOT/qr.png  ->  $BOOTSTRAP_URL"
else
  echo "WARN: qrencode not installed — page will not show a QR code" >&2
  echo "      apt install qrencode and re-run to add it" >&2
fi

# ── caddy site snippet ───────────────────────────────────────────────────────
echo "== caddy site =="
install -D -m 0644 "$HERE/ca.caddy" "$SITE"
echo "  $SITE"

# ── reload caddy ─────────────────────────────────────────────────────────────
echo "== caddy reload =="
if systemctl is-active --quiet caddy; then
  systemctl reload caddy
  echo "  caddy reloaded — picked up ca.dobby.lan + HTTP bootstrap"
else
  echo "  caddy not running — start it to pick up the new site" >&2
fi

echo
echo "Done."
echo "  bootstrap:   $BOOTSTRAP_URL              (no DNS, no cert — for first contact)"
echo "  clean URL:   https://ca.dobby.lan/             (needs DNS + cert trust)"
echo "  quick test:  curl -s $BOOTSTRAP_URL | head -3"
