#!/bin/bash
set -e
echo "========================================"
echo "  TilinX PROXY - Installer"
echo "========================================"
cd "$(dirname "$0")"
BASE_DIR="$(pwd)"
mkdir -p "$BASE_DIR/data/TilinX" "$BASE_DIR/logs" "$BASE_DIR/certs"

echo "[1/3] Installing system dependencies..."
if command -v apt-get &>/dev/null; then
    sudo apt-get update -qq && sudo apt-get install -y -qq python3 python3-pip curl 2>/dev/null || true
fi

echo "[2/3] Installing Python dependencies..."
pip install -r requirements.txt --quiet
pip install mitmproxy python-telegram-bot requests flask --quiet

echo "[3/3] Done!"
echo ""
echo "========================================"
echo "  Quick Start:"
echo "========================================"
echo ""
echo "  # 1. Set your env vars (edit .env or export):"
echo "  export TilinX_BOT_TOKEN=\"your_bot_token\""
echo "  export TilinX_ADMIN_ID=\"your_telegram_id\""
echo ""
echo "  # 2. Start everything (proxy + bot):"
echo "  bash start_all.sh"
echo ""
echo "  # 3. Or start only the proxy:"
echo "  bash start_proxy.sh"
echo ""
echo "  # 4. Check status:"
echo "  bash status.sh"
echo ""
echo "  # 5. Stop all:"
echo "  bash stop_all.sh"
echo ""
