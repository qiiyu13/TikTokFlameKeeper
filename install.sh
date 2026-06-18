#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="/opt/tiktok-flamekeeper"
CONFIG_DEST="$HOME/.tiktok-flamekeeper/config.json"

echo "=== TikTok FlameKeeper Install ==="
echo ""

# System deps for Playwright Chromium.
# Best-effort: package names differ across Ubuntu releases (e.g. libasound2 ->
# libasound2t64 on 24.04). `playwright install --with-deps` below is the
# authoritative step, so don't abort the whole install if one name is stale.
echo "[1/6] Installing system dependencies..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3 python3-pip python3-venv > /dev/null
sudo apt-get install -y -qq \
    libnss3 libnspr4 libatk-bridge2.0-0 libdrm2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxrandr2 \
    libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    libatspi2.0-0 libcups2 libx11-xcb1 > /dev/null 2>&1 || true

# Copy project files
echo "[2/6] Installing project files..."
sudo mkdir -p "$INSTALL_DIR"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
sudo cp "$SCRIPT_DIR"/main.py "$SCRIPT_DIR"/browser.py "$SCRIPT_DIR"/db.py "$SCRIPT_DIR"/sentinel.py "$INSTALL_DIR/"
sudo cp "$SCRIPT_DIR"/requirements.txt "$INSTALL_DIR/"
sudo cp "$SCRIPT_DIR"/config.json.example "$INSTALL_DIR/"

# Python deps. Ubuntu 24.04 marks the system env "externally managed" (PEP 668),
# so retry with --break-system-packages if the plain install is refused.
echo "[3/6] Installing Python dependencies..."
sudo pip3 install -q -r "$INSTALL_DIR/requirements.txt" || \
    sudo pip3 install -q --break-system-packages -r "$INSTALL_DIR/requirements.txt"

# Playwright browser
echo "[4/6] Installing Chromium for Playwright..."
sudo python3 -m playwright install chromium --with-deps > /dev/null 2>&1 || \
    sudo python3 -m playwright install chromium

# Config
echo "[5/6] Setting up config..."
if [ ! -f "$CONFIG_DEST" ]; then
    mkdir -p "$(dirname "$CONFIG_DEST")"
    cp "$INSTALL_DIR/config.json.example" "$CONFIG_DEST"
    echo "  Config created at $CONFIG_DEST"
    echo "  >>> EDIT THIS FILE with your targets and messages before using! <<<"
else
    echo "  Config already exists at $CONFIG_DEST (skipped)"
fi

# Systemd timer
echo "[6/6] Installing systemd timer..."
SVC_FILE="/etc/systemd/system/tiktok-flamekeeper.service"
TIMER_FILE="/etc/systemd/system/tiktok-flamekeeper.timer"

sudo tee "$SVC_FILE" > /dev/null <<EOF
[Unit]
Description=TikTok FlameKeeper — Daily DM Streak Automation
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=root
WorkingDirectory=$INSTALL_DIR
ExecStart=/usr/bin/python3 $INSTALL_DIR/main.py run
StandardOutput=journal
StandardError=journal
EOF

sudo tee "$TIMER_FILE" > /dev/null <<EOF
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
echo "=== Installation complete ==="
echo ""
echo "Next steps (see DEPLOY.md for the full guide):"
echo "  1. Edit config:    nano $CONFIG_DEST"
echo "  2. Log in LOCALLY: python3 main.py setup   (needs a display)"
echo "  3. Move session:   scp cookies.json to droplet, then"
echo "                     python3 $INSTALL_DIR/main.py import-cookies /root/cookies.json"
echo "  4. Verify:         python3 $INSTALL_DIR/main.py test   (expect Login: OK)"
echo "  5. Set timezone:   sudo timedatectl set-timezone <your/zone>"
echo "  6. Check logs:     journalctl -u tiktok-flamekeeper -f"
