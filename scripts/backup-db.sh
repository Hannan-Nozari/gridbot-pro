#!/bin/bash
# ──────────────────────────────────────────────────────────
#  GridBot DB backup script
#  Uses SQLite .backup command for safe online backup
#  Keeps the last 30 daily backups, last 12 weekly, last 6 monthly
# ──────────────────────────────────────────────────────────

set -euo pipefail

DATA_DIR="/opt/gridbot/data"
BACKUP_DIR="/opt/gridbot/backups"
DB_FILE="$DATA_DIR/trading.db"
TIMESTAMP=$(date +"%Y-%m-%d_%H-%M-%S")
DAY_OF_WEEK=$(date +%u)
DAY_OF_MONTH=$(date +%d)

mkdir -p "$BACKUP_DIR/daily" "$BACKUP_DIR/weekly" "$BACKUP_DIR/monthly"

if [ ! -f "$DB_FILE" ]; then
    echo "[$(date)] DB file not found at $DB_FILE — skipping backup"
    exit 0
fi

# Daily backup
BACKUP_FILE="$BACKUP_DIR/daily/trading_${TIMESTAMP}.db"

if command -v sqlite3 >/dev/null 2>&1; then
    # Use SQLite online backup (safe even if the DB is being written to)
    sqlite3 "$DB_FILE" ".backup '$BACKUP_FILE'"
    echo "[$(date)] Online backup -> $BACKUP_FILE"
else
    # Fallback: file copy (safe because WAL mode is used)
    cp "$DB_FILE" "$BACKUP_FILE"
    echo "[$(date)] Copy backup -> $BACKUP_FILE"
fi

gzip -f "$BACKUP_FILE"
BACKUP_FILE="${BACKUP_FILE}.gz"
echo "[$(date)] Compressed -> $BACKUP_FILE"

# Weekly — on Sundays
if [ "$DAY_OF_WEEK" = "7" ]; then
    cp "$BACKUP_FILE" "$BACKUP_DIR/weekly/"
    echo "[$(date)] Weekly snapshot created"
fi

# Monthly — on the 1st
if [ "$DAY_OF_MONTH" = "01" ]; then
    cp "$BACKUP_FILE" "$BACKUP_DIR/monthly/"
    echo "[$(date)] Monthly snapshot created"
fi

# Rotation — prune older backups
find "$BACKUP_DIR/daily" -name "*.gz" -mtime +30 -delete 2>/dev/null || true
find "$BACKUP_DIR/weekly" -name "*.gz" -mtime +90 -delete 2>/dev/null || true
find "$BACKUP_DIR/monthly" -name "*.gz" -mtime +365 -delete 2>/dev/null || true

# Summary
DAILY_COUNT=$(find "$BACKUP_DIR/daily" -name "*.gz" 2>/dev/null | wc -l)
WEEKLY_COUNT=$(find "$BACKUP_DIR/weekly" -name "*.gz" 2>/dev/null | wc -l)
MONTHLY_COUNT=$(find "$BACKUP_DIR/monthly" -name "*.gz" 2>/dev/null | wc -l)
TOTAL_SIZE=$(du -sh "$BACKUP_DIR" 2>/dev/null | cut -f1)

echo "[$(date)] Backup complete. Daily: $DAILY_COUNT, Weekly: $WEEKLY_COUNT, Monthly: $MONTHLY_COUNT, Total size: $TOTAL_SIZE"
