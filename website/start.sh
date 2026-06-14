#!/bin/bash
# ─── TilinX Website - Quick Start ──────────────────────
cd "$(dirname "$0")"
export TilinX_WEB_PORT=${TilinX_WEB_PORT:-8080}
if [ -z "$TilinX_DASH_PASSWORD" ]; then
    echo "  ⚠️  TilinX_DASH_PASSWORD no está definido"
fi
echo "════════════════════════════════════════════"
echo "  TilinX Web - :$TilinX_WEB_PORT"
echo "════════════════════════════════════════════"
pip install -r requirements.txt -q
python app.py
