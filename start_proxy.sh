#!/bin/bash
set -e
cd "$(dirname "$0")"
BASE_DIR="$(pwd)"
export TilinX_BASE_DIR="$BASE_DIR"
export TilinX_DB_PATH="$BASE_DIR/ips.json"
export TilinX_LOG_DIR="$BASE_DIR/logs"
export TilinX_DATA_DIR="$BASE_DIR/data/TilinX"
export TilinX_PROXY_PORT="${TilinX_PROXY_PORT:-8884}"

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

echo "[TilinX] Starting Proxy on port $TilinX_PROXY_PORT..."
echo "[TilinX] Proxy Auth: $TilinX_PROXY_AUTH_USER:$TilinX_PROXY_AUTH_PASS"
exec mitmdump -p "$TilinX_PROXY_PORT" \
    --set proxyauth="${TilinX_PROXY_AUTH_USER}:${TilinX_PROXY_AUTH_PASS}" \
    --set block_global=false \
    --ssl-insecure \
    -s "$BASE_DIR/tilinx_proxy.py"
