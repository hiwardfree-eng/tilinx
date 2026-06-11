#!/bin/bash
echo "========================================"
echo " TilinX - Stopping Services"
echo "========================================"
pkill -f "tilinx_proxy.py" && echo "  [OK] Proxy  stopped" || echo "  [..] Proxy  not running"
pkill -f "bot_control.py"  && echo "  [OK] Bot    stopped" || echo "  [..] Bot    not running"
pkill -f "mitmdump"        && echo "  [OK] mitmdump cleaned" || true
echo "========================================"
