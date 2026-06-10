#!/bin/bash
# ─── TilinX Backup ───────────────────────────────────────
# Uso: bash backup.sh [output_dir]

BASE_DIR="/home/runner/tilinx"
OUTPUT_DIR="${1:-$BASE_DIR/backups}"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
mkdir -p "$OUTPUT_DIR"

echo "[TilinX Backup] Starting at $(date)"

# Backup ips.json
if [ -f "$BASE_DIR/ips.json" ]; then
    cp "$BASE_DIR/ips.json" "$OUTPUT_DIR/ips_backup_$TIMESTAMP.json"
    echo "  ✅ ips.json backed up"
fi

# Backup logs
if [ -d "$BASE_DIR/logs" ]; then
    tar -czf "$OUTPUT_DIR/logs_$TIMESTAMP.tar.gz" -C "$BASE_DIR" logs/ 2>/dev/null
    echo "  ✅ Logs archived"
fi

# Backup data
if [ -d "$BASE_DIR/data" ]; then
    tar -czf "$OUTPUT_DIR/data_$TIMESTAMP.tar.gz" -C "$BASE_DIR" data/ 2>/dev/null
    echo "  ✅ Data archived"
fi

# Clean old backups (keep last 30)
find "$OUTPUT_DIR" -name "ips_backup_*.json" -mtime +30 -delete 2>/dev/null
find "$OUTPUT_DIR" -name "*.tar.gz" -mtime +30 -delete 2>/dev/null

echo "[TilinX Backup] Done → $OUTPUT_DIR"
