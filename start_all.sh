#!/bin/bash
echo "========================================"
echo " TilinX PROXY - Starting Services"
echo "========================================"
BASE_DIR=/home/runner/tilinx
DB_PATH=$BASE_DIR/ips.json
LOG_DIR=$BASE_DIR/logs
DATA_DIR=$BASE_DIR/data/TilinX

echo "[1/2] Starting Proxy Port 8884..."
TilinX_BASE_DIR=$BASE_DIR TilinX_DB_PATH=$DB_PATH TilinX_LOG_DIR=$LOG_DIR TilinX_DATA_DIR=$DATA_DIR \
mitmdump -p 8884 --set proxyauth=TilinX:TilinX --set block_global=false --ssl-insecure \
-s $BASE_DIR/tilinx_proxy.py > $LOG_DIR/proxy.out 2>&1 &
sleep 2

echo "[2/2] Starting Bot..."
TilinX_DB_PATH=$DB_PATH TilinX_LOG_DIR=$LOG_DIR TilinX_DATA_DIR=$DATA_DIR \
python3 $BASE_DIR/bot_control.py > $LOG_DIR/bot.out 2>&1 &

echo "Done! Check status: bash status.sh"
