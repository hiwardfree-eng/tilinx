#!/bin/bash
echo "========================================"
echo " TilinX - Stopping Services"
echo "========================================"
cd "$(dirname "$0")"
RUN_DIR="./run"
mkdir -p "$RUN_DIR"

for SERVICE in proxy bot; do
    PID_FILE="$RUN_DIR/$SERVICE.pid"
    if [ -f "$PID_FILE" ]; then
        PID=$(cat "$PID_FILE")
        if kill "$PID" 2>/dev/null; then
            echo "  [OK] $SERVICE (PID $PID) stopped"
        else
            echo "  [..] $SERVICE not running (PID $PID stale)"
        fi
        rm -f "$PID_FILE"
    else
        echo "  [..] $SERVICE no PID file"
    fi
done

# Clean up leftover mitmdump processes belonging to this project
if pgrep -f "tilinx_proxy.py" > /dev/null 2>&1; then
    pkill -f "tilinx_proxy.py" 2>/dev/null && echo "  [OK] Proxy (fallback) cleaned" || true
fi
if pgrep -f "mitmdump.*tilinx" > /dev/null 2>&1; then
    pkill -f "mitmdump.*tilinx" 2>/dev/null && echo "  [OK] mitmdump (tilinx) cleaned" || true
fi

echo "========================================"
