#!/bin/bash
set -e
echo "========================================"
echo " TilinX PROXY - Starting Services"
echo "========================================"
cd "$(dirname "$0")"
BASE_DIR="$(pwd)"
export TilinX_BASE_DIR="$BASE_DIR"
export TilinX_DB_PATH="$BASE_DIR/ips.json"
export TilinX_LOG_DIR="$BASE_DIR/logs"
export TilinX_DATA_DIR="$BASE_DIR/data/TilinX"
export TilinX_PROXY_PORT="${TilinX_PROXY_PORT:-8884}"

mkdir -p "$TilinX_LOG_DIR"

# ─── Auto-generate unique proxy credentials ─────────────
AUTH_FILE="$BASE_DIR/.proxy.auth"
if [ -z "$TilinX_PROXY_AUTH_USER" ] || [ -z "$TilinX_PROXY_AUTH_PASS" ]; then
    if [ -f "$AUTH_FILE" ]; then
        source "$AUTH_FILE"
    else
        TilinX_PROXY_AUTH_USER=$(python3 -c "import secrets; print(secrets.token_hex(8))")
        TilinX_PROXY_AUTH_PASS=$(python3 -c "import secrets; print(secrets.token_hex(16))")
        echo "TilinX_PROXY_AUTH_USER=$TilinX_PROXY_AUTH_USER" > "$AUTH_FILE"
        echo "TilinX_PROXY_AUTH_PASS=$TilinX_PROXY_AUTH_PASS" >> "$AUTH_FILE"
        chmod 600 "$AUTH_FILE"
    fi
fi

echo "[1/2] Starting Proxy on port $TilinX_PROXY_PORT..."
echo "  Auth: $TilinX_PROXY_AUTH_USER:$TilinX_PROXY_AUTH_PASS"
mitmdump -p "$TilinX_PROXY_PORT" \
    --set proxyauth="${TilinX_PROXY_AUTH_USER}:${TilinX_PROXY_AUTH_PASS}" \
    --set block_global=false \
    --ssl-insecure \
    -s "$BASE_DIR/tilinx_proxy.py" \
    > "$TilinX_LOG_DIR/proxy.out" 2>&1 &
PROXY_PID=$!
echo "  Proxy PID: $PROXY_PID"
sleep 2

echo "[2/2] Starting Bot..."
python3 "$BASE_DIR/bot_control.py" \
    > "$TilinX_LOG_DIR/bot.out" 2>&1 &
BOT_PID=$!
echo "  Bot PID: $BOT_PID"

echo ""
echo "========================================"
echo "  All services started!"
echo "  Proxy PID: $PROXY_PID"
echo "  Bot PID:   $BOT_PID"
echo "  Logs: $TilinX_LOG_DIR/"
echo "  Check: bash status.sh"
echo "  Stop:  bash stop_all.sh"
echo "========================================"
