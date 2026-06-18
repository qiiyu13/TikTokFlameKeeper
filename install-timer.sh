#!/usr/bin/env bash
# Installs (or repairs) the systemd timer for an already-working install.
# Run from the repo dir on the server:
#   cd ~/TikTokFlameKeeper && git pull && bash install-timer.sh
# No config text to paste — paths are derived automatically.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
PY="$REPO_DIR/.venv/bin/python"
USER_NAME="$(whoami)"
TZ_NAME="${TZ_NAME:-Asia/Jakarta}"

[ -x "$PY" ] || { echo "ERROR: venv python not found at $PY — set up the venv first"; exit 1; }

echo "Installing timer: user=$USER_NAME dir=$REPO_DIR tz=$TZ_NAME"

sudo tee /etc/systemd/system/tiktok-flamekeeper.service > /dev/null <<EOF
[Unit]
Description=TikTok FlameKeeper — Daily DM Streak
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=$USER_NAME
WorkingDirectory=$REPO_DIR
ExecStart=$PY $REPO_DIR/main.py run
StandardOutput=journal
StandardError=journal
EOF

sudo tee /etc/systemd/system/tiktok-flamekeeper.timer > /dev/null <<EOF
[Unit]
Description=Daily TikTok FlameKeeper trigger
Requires=tiktok-flamekeeper.service

[Timer]
OnCalendar=*-*-* 09:00:00
RandomizedDelaySec=7200
Persistent=true

[Install]
WantedBy=timers.target
EOF

sudo timedatectl set-timezone "$TZ_NAME"
sudo systemctl daemon-reload
sudo systemctl enable --now tiktok-flamekeeper.timer

echo ""
echo "Done. Next run:"
systemctl list-timers tiktok-flamekeeper.timer --no-pager || true
