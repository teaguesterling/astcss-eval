#!/bin/sh
# install-apt-install.sh — NOPASSWD installer for named packages from the
# configured (official, signed) apt repos only.
#
# Pure sudoers can't restrict apt to official repos: its wildcard matching
# is too coarse and apt has escape hatches (local .deb install, `-o` option
# injection). So we grant NOPASSWD only to a root-owned wrapper that
# validates its arguments and forwards bare package names to apt-get.
# apt-get with bare names pulls solely from configured repos.
#
# After install:
#   sudo apt-install <pkg>...   # installs from official repos, no password
#
# Run as:
#   sudo sh sudo/install-apt-install.sh
#
# Idempotent — safe to re-run.

set -e

if [ "$(id -u)" -ne 0 ]; then
    echo "must be root; run with: sudo sh $0" >&2
    exit 1
fi

USER_NAME="${SUDO_USER:-teague}"

install -d -m 0755 /usr/local/sbin

cat > /usr/local/sbin/apt-install <<'INNER'
#!/bin/sh
# apt-install — install NAMED packages from configured repos only.
# Rejects options, paths, local .debs, and version pins so the only thing
# that can reach apt-get is a bare package name from a signed repo.
set -e
[ "$#" -ge 1 ] || { echo "usage: apt-install PKG..." >&2; exit 1; }
for pkg in "$@"; do
    case "$pkg" in
        -*|*/*|*.deb|*=*)
            echo "refused: '$pkg' (bare package names only — no options, paths, .debs, or version pins)" >&2
            exit 1 ;;
        [a-z0-9]*) : ;;
        *)
            echo "refused: '$pkg'" >&2
            exit 1 ;;
    esac
done
exec apt-get install -y "$@"
INNER
chmod 0755 /usr/local/sbin/apt-install

cat > /etc/sudoers.d/apt-install <<EOF
$USER_NAME ALL=(root) NOPASSWD: /usr/local/sbin/apt-install
EOF
chmod 0440 /etc/sudoers.d/apt-install

# Validate the sudoers fragment before declaring victory.
visudo -c -q

echo "installed /usr/local/sbin/apt-install"
echo "installed /etc/sudoers.d/apt-install (NOPASSWD for $USER_NAME)"
echo "now: 'sudo apt-install <pkg>' installs from official repos without a password."
