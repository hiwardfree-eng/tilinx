#!/bin/bash
# ─── TilinX Website - Quick Start ──────────────────────
cd "$(dirname "$0")"
export TilinX_WEB_PORT=${TilinX_WEB_PORT:-8080}
export TilinX_DASH_PASSWORD=${TilinX_DASH_PASSWORD:-hw132319}
echo "════════════════════════════════════════════"
echo "  TilinX Web - :$TilinX_WEB_PORT"
echo "  Password: $TilinX_DASH_PASSWORD"
echo "════════════════════════════════════════════"
pip install -r requirements.txt -q
python website.py
