#!/bin/bash
set -e
cd "$(dirname "$0")"
BASE_DIR="$(pwd)"
export TilinX_BASE_DIR="$BASE_DIR"
export TilinX_DB_PATH="$BASE_DIR/ips.json"
export TilinX_LOG_DIR="$BASE_DIR/logs"
export TilinX_DATA_DIR="$BASE_DIR/data/TilinX"
export TilinX_PROXY_PORT="${TilinX_PROXY_PORT:-8884}"

echo "[TilinX] Starting Proxy on port $TilinX_PROXY_PORT..."
exec mitmdump -p "$TilinX_PROXY_PORT" \
    --set proxyauth="${TilinX_PROXY_AUTH_USER:-TilinX}:${TilinX_PROXY_AUTH_PASS:-TilinX}" \
    --set block_global=false \
    --ssl-insecure \
    -s "$BASE_DIR/tilinx_proxy.py"
