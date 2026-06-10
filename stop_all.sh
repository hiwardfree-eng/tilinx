#!/bin/bash
pkill -f "tilinx_proxy.py" && echo "Proxy stopped" || echo "Proxy not running"
pkill -f "bot_control.py"  && echo "Bot stopped"   || echo "Bot not running"
