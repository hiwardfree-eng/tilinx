#!/bin/bash
# ─── TilinX Dashboard Starter ────────────────────────────
export TilinX_ENV=production
export TilinX_DASHBOARD_PORT=${TilinX_DASHBOARD_PORT:-5000}
export TilinX_DASH_PASSWORD="${TilinX_DASH_PASSWORD:-admin}"
echo "[TilinX] Starting Dashboard on :$TilinX_DASHBOARD_PORT"
pip install flask -q
python3 /home/runner/tilinx/src/dashboard.py
