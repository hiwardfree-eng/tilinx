#!/bin/bash
# Auto-heal: checks proxy & web are running, restarts if dead
# Install in cron: */5 * * * * /opt/tilinx/deploy/autoheal.sh

PROXY_PORT="${TilinX_PROXY_PORT:-8884}"
WEB_PORT="${TilinX_WEB_PORT:-8080}"
LOG="/var/log/tilinx/autoheal.log"

echo "[$(date '+%Y-%m-%d %H:%M:%S')] Health check..." >> "$LOG"

# 1. Check proxy
if ! curl -sf -x "http://127.0.0.1:$PROXY_PORT" http://httpbin.org/get --max-time 10 > /dev/null 2>&1; then
    echo "  Proxy DOWN -> restarting" >> "$LOG"
    systemctl restart tilinx-proxy 2>> "$LOG"
    echo "  Proxy restarted" >> "$LOG"
fi

# 2. Check web
if ! curl -sf "http://127.0.0.1:$WEB_PORT/api/health" --max-time 10 > /dev/null 2>&1; then
    echo "  Web DOWN -> restarting" >> "$LOG"
    systemctl restart tilinx-web 2>> "$LOG"
    echo "  Web restarted" >> "$LOG"
fi

# 3. Log disk & memory
DISK=$(df / | tail -1 | awk '{print $5}')
RAM=$(free | grep Mem | awk '{printf "%.0f", $3/$2 * 100}')
echo "  Disk: $DISK  RAM: $RAM%" >> "$LOG"
