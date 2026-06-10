#!/bin/bash
# ─── TilinX Reports ──────────────────────────────────────
# Genera reports diarios, semanales, mensuales
cd "$(dirname "$0")/.."
export TilinX_ENV=production
python3 scripts/reports.py
echo "Reports generated in $(pwd)"
