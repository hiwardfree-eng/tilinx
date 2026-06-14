#!/bin/bash
# ─── TilinX VPS Setup — Run this on the VPS as root ──────────
set -e

INSTALL_DIR="/opt/tilinx"
SRC_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "========================================"
echo "  TilinX VPS Setup"
echo "========================================"

# 1. Install system deps
echo "[1/6] Installing system dependencies..."
apt-get update -qq
apt-get install -y -qq python3 python3-pip python3-venv curl netcat-openbsd 2>&1 | tail -1

# 2. Install mitmproxy
echo "[2/6] Installing mitmproxy..."
pip3 install mitmproxy 2>&1 | tail -1

# 3. Copy files
echo "[3/6] Copying to $INSTALL_DIR..."
mkdir -p "$INSTALL_DIR"
rsync -a --delete \
    --exclude='.git' --exclude='__pycache__' --exclude='*.pyc' \
    --exclude='.backups' --exclude='venv' \
    "$SRC_DIR/" "$INSTALL_DIR/"

# 4. Create directories & .env
echo "[4/6] Creating directories..."
mkdir -p /var/log/tilinx
mkdir -p "$INSTALL_DIR/logs"
mkdir -p "$INSTALL_DIR/data"

if [ ! -f "$INSTALL_DIR/.env" ]; then
    cp "$INSTALL_DIR/.env.example" "$INSTALL_DIR/.env"
    echo "  >> EDIT THIS FILE: nano $INSTALL_DIR/.env"
fi

# 5. Install Python deps
echo "[5/6] Installing Python packages..."
pip3 install -r "$INSTALL_DIR/requirements.txt" 2>&1 | tail -1 || true
pip3 install flask flask-sqlalchemy gunicorn psutil 2>&1 | tail -1

# 6. Setup systemd services
echo "[6/6] Installing systemd services..."
cp "$INSTALL_DIR/deploy/tilinx-proxy.service" /etc/systemd/system/
cp "$INSTALL_DIR/deploy/tilinx-web.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable tilinx-proxy tilinx-web
systemctl start tilinx-proxy tilinx-web

# Auto-heal cron
cp "$INSTALL_DIR/deploy/autoheal.sh" /opt/tilinx/autoheal.sh
chmod +x /opt/tilinx/autoheal.sh
(crontab -l 2>/dev/null; echo "*/5 * * * * /opt/tilinx/autoheal.sh") | crontab -

echo "========================================"
echo "  Setup complete!"
echo ""
echo "  Status:"
systemctl status tilinx-proxy --no-pager 2>&1 | head -3
systemctl status tilinx-web --no-pager 2>&1 | head -3
echo ""
echo "  LOGS:"
echo "    Proxy: journalctl -u tilinx-proxy -f"
echo "    Web:   journalctl -u tilinx-web -f"
echo ""
echo "  EDIT: nano $INSTALL_DIR/.env"
echo "  Then: systemctl restart tilinx-proxy tilinx-web"
echo "========================================"
