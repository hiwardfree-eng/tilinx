#!/bin/bash
echo "========================================"
echo "  TilinX PROXY - Installer"
echo "  TilinX"
echo "========================================"
BASE_DIR="/home/runner/tilinx"
mkdir -p $BASE_DIR/{data/TilinX,logs,certs}

echo "[1/3] Copying files..."
cp config.py    $BASE_DIR/
cp logger.py   $BASE_DIR/
cp database.py $BASE_DIR/
cp cache.py    $BASE_DIR/
cp utils.py    $BASE_DIR/
cp bot_control.py $BASE_DIR/
cp tilinx_proxy.py $BASE_DIR/
cp -r data/TilinX/* $BASE_DIR/data/TilinX/ 2>/dev/null || true
[ -f ips.json ] && cp ips.json $BASE_DIR/ || echo '{}' > $BASE_DIR/ips.json
[ -f keys.json ] && cp keys.json $BASE_DIR/ || echo '{}' > $BASE_DIR/keys.json
chmod +x $BASE_DIR/*.py

echo "[2/3] Installing dependencies..."
pip install mitmproxy python-telegram-bot requests flask --quiet

echo "[3/3] Done!"
echo ""
echo "Set env vars then run:"
echo "  TilinX_BOT_TOKEN=<token> TilinX_ADMIN_ID=<id> bash start_all.sh"
echo ""
echo "For proxy:"
echo "  TilinX_PROXY_ENABLED=1 TilinX_PROXY_URL=socks5://user:pass@ip:1080"
