#!/bin/bash
set -e
cd "$(dirname "$0")"
BASE_DIR="$(pwd)"

# ─── Load .env if exists ─────────────────────────
[ -f "$BASE_DIR/.env" ] && set -a && source "$BASE_DIR/.env" && set +a

export TilinX_BASE_DIR="$BASE_DIR"
export TilinX_DB_PATH="$BASE_DIR/ips.json"
export TilinX_LOG_DIR="$BASE_DIR/logs"
export TilinX_DATA_DIR="$BASE_DIR/data/TilinX"
export TilinX_PROXY_PORT="${TilinX_PROXY_PORT:-8884}"

if [ -n "$TilinX_ADMIN_IP_WHITELIST" ]; then
    echo "[TilinX] Admin IPs: $TilinX_ADMIN_IP_WHITELIST"
fi
echo "[TilinX] Starting Proxy on port $TilinX_PROXY_PORT..."
echo "[TilinX] Auth: IP database ($TilinX_DB_PATH)"
exec mitmdump -p "$TilinX_PROXY_PORT" \
    --set block_global=false \
    --ssl-insecure \
    -s "$BASE_DIR/tilinx_proxy.py"
