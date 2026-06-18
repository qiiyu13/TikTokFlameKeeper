#!/usr/bin/env bash
# Run this ON YOUR LAPTOP. Packages your logged-in session + config, ships them
# to the droplet, and runs the server setup. You only answer the sudo password.
#
#   ./deploy.sh
#
# Override defaults via env if needed:
#   SSH_KEY=mykey REMOTE=user@host TZ_NAME=Asia/Jakarta ./deploy.sh
set -euo pipefail

SSH_KEY="${SSH_KEY:-mediku}"
REMOTE="${REMOTE:-mediku@100.71.104.8}"
TZ_NAME="${TZ_NAME:-Asia/Jakarta}"
LOCAL_FK="$HOME/.tiktok-flamekeeper"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

[ -f "$SSH_KEY" ] || echo "note: SSH key '$SSH_KEY' not in current dir — relying on ssh config"

if [ ! -d "$LOCAL_FK/profile" ]; then
    echo "ERROR: no logged-in profile at $LOCAL_FK/profile"
    echo "Run 'python3 main.py setup' locally and log into TikTok first."
    exit 1
fi
if [ ! -f "$LOCAL_FK/config.json" ]; then
    echo "ERROR: no config at $LOCAL_FK/config.json"
    exit 1
fi

echo "== packaging session + config =="
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
tar czf "$TMP/profile.tgz" -C "$LOCAL_FK" --exclude 'Singleton*' profile
cp "$LOCAL_FK/config.json" "$TMP/config.json"

echo "== uploading to $REMOTE =="
scp -i "$SSH_KEY" \
    "$TMP/profile.tgz" "$TMP/config.json" "$SCRIPT_DIR/server_setup.sh" \
    "$REMOTE:/tmp/"

echo "== running remote setup (enter sudo password when prompted) =="
ssh -t -i "$SSH_KEY" "$REMOTE" "TZ_NAME='$TZ_NAME' bash /tmp/server_setup.sh"

echo "== deploy complete =="
