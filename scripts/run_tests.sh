#!/bin/bash
# ─── Run Tests ───────────────────────────────────────────
set -e
echo "========================================"
echo " TilinX - Running Tests"
echo "========================================"

cd "$(dirname "$0")/.."
export TilinX_ENV=testing
export TilinX_BOT_TOKEN=test_token
export TilinX_ADMIN_ID=999

# Unit tests
python -m pytest tests/ -v --tb=short 2>/dev/null || python -m unittest tests/test_all.py -v

echo ""
echo "========================================"
echo " Tests complete"
echo "========================================"
