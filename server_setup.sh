#!/usr/bin/env bash
# Runs ON THE DROPLET. Invoked by deploy.sh — you normally don't run this by hand.
# Expects /tmp/profile.tgz and /tmp/config.json already uploaded.
set -euo pipefail

REPO_URL="https://github.com/qiiyu13/TikTokFlameKeeper.git"
REPO_DIR="$HOME/TikTokFlameKeeper"
FK="$HOME/.tiktok-flamekeeper"
TZ_NAME="${TZ_NAME:-Asia/Jakarta}"
USER_NAME="$(whoami)"

echo "[1/6] system packages"
sudo apt-get update -qq
sudo apt-get install -y python3 python3-pip python3-venv git

echo "[2/6] project code"
if [ -d "$REPO_DIR/.git" ]; then
    git -C "$REPO_DIR" pull --ff-only || true
else
    git clone "$REPO_URL" "$REPO_DIR"
fi
cd "$REPO_DIR"

echo "[3/6] python venv + deps + chromium"
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python -m playwright install --with-deps chromium

echo "[4/6] install session + config"
mkdir -p "$FK"
rm -rf "$FK/profile"
tar xzf /tmp/profile.tgz -C "$FK"
cp /tmp/config.json "$FK/config.json"

echo "[5/6] verify login"
.venv/bin/python main.py test

echo "[6/6] systemd timer (daily 09:00 + up to 2h jitter, $TZ_NAME)"
sudo timedatectl set-timezone "$TZ_NAME"
sudo tee /etc/systemd/system/tiktok-flamekeeper.service > /dev/null <<EOF
[Unit]
Description=TikTok FlameKeeper — Daily DM Streak
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=$USER_NAME
WorkingDirectory=$REPO_DIR
ExecStart=$REPO_DIR/.venv/bin/python $REPO_DIR/main.py run
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
sudo systemctl daemon-reload
sudo systemctl enable --now tiktok-flamekeeper.timer

echo ""
echo "== setup complete =="
systemctl list-timers tiktok-flamekeeper.timer --no-pager || true
echo ""
echo "Logs:        journalctl -u tiktok-flamekeeper -f"
echo "Run now:     sudo systemctl start tiktok-flamekeeper.service"
echo "History:     $REPO_DIR/.venv/bin/python $REPO_DIR/main.py log --n 5"
