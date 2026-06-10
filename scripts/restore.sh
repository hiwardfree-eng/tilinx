#!/bin/bash
# ─── TilinX Restore ──────────────────────────────────────
# Uso: bash restore.sh <backup_file>

if [ -z "$1" ]; then
    echo "Usage: bash restore.sh <backup_file>"
    echo "Example: bash restore.sh backups/uids_backup_20260101_120000.json"
    exit 1
fi

BACKUP_FILE="$1"
BASE_DIR="/home/runner/tilinx"

if [ ! -f "$BACKUP_FILE" ]; then
    echo "❌ Backup file not found: $BACKUP_FILE"
    exit 1
fi

echo "[TilinX Restore] Restoring from $BACKUP_FILE ..."
cp "$BACKUP_FILE" "$BASE_DIR/ips.json"

if [ $? -eq 0 ]; then
    echo "✅ Restore completed successfully"
else
    echo "❌ Restore failed"
    exit 1
fi
