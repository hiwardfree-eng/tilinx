#!/bin/bash
export TilinX_BOT_TOKEN="${TilinX_BOT_TOKEN}"
export TilinX_ADMIN_ID="${TilinX_ADMIN_ID}"
export TilinX_DB_PATH=/home/runner/tilinx/ips.json
export TilinX_LOG_DIR=/home/runner/tilinx/logs
export TilinX_DATA_DIR=/home/runner/tilinx/data/TilinX
export TilinX_PROXY_ENABLED="${TilinX_PROXY_ENABLED:-0}"
export TilinX_PROXY_URL="${TilinX_PROXY_URL}"
export TilinX_PROXY_TYPE="${TilinX_PROXY_TYPE:-socks5}"
echo "[TilinX] Starting Bot..."
python3 /home/runner/tilinx/bot_control.py
