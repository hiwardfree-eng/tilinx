#!/bin/bash
export TilinX_BASE_DIR=/home/runner/tilinx
export TilinX_DB_PATH=/home/runner/tilinx/ips.json
export TilinX_LOG_DIR=/home/runner/tilinx/logs
export TilinX_DATA_DIR=/home/runner/tilinx/data/TilinX
echo "[TilinX] Starting Proxy on port 8884..."
mitmdump -p 8884 --set proxyauth=TilinX:TilinX --set block_global=false --ssl-insecure -s /home/runner/tilinx/tilinx_proxy.py
