#!/bin/bash
echo "========================================"
echo " TilinX PROXY - Status"
echo "========================================"
cd "$(dirname "$0")"
RUN_DIR="./run"

check_service() {
    local name=$1
    local pid_file="$RUN_DIR/$2.pid"
    local display=$3
    if [ -f "$pid_file" ]; then
        PID=$(cat "$pid_file")
        if kill -0 "$PID" 2>/dev/null; then
            echo "  [ON]  $display  (PID: $PID)"
        else
            echo "  [OFF] $display  (PID file stale)"
        fi
    else
        pids=$(pgrep -f "$2" 2>/dev/null)
        [ -n "$pids" ] && echo "  [ON]  $display  (PID: $(echo $pids | tr '\n' ' '))" || echo "  [OFF] $display"
    fi
}

check_service "Proxy" "tilinx_proxy.py" "Proxy 8884"
check_service "Bot" "bot_control.py" "Bot"
echo "========================================"
