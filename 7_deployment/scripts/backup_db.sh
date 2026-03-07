#!/bin/bash
# ══════════════════════════════════════════════════════════════
#  ReconMind — Database Backup Script
#
#  Usage:
#    ./scripts/backup_db.sh              → manual backup
#    Add to cron for automated backups:
#    0 2 * * * /path/to/scripts/backup_db.sh
# ══════════════════════════════════════════════════════════════

set -e

BACKUP_DIR="./backups"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/reconmind_$TIMESTAMP.sql.gz"
RETENTION_DAYS=7

# Load env
source .env 2>/dev/null || true

POSTGRES_USER="${POSTGRES_USER:-reconmind}"
POSTGRES_DB="${POSTGRES_DB:-reconmind}"

mkdir -p "$BACKUP_DIR"

echo "[Backup] Starting database backup..."

# Run pg_dump inside DB container, compress output
docker exec reconmind_db pg_dump \
    -U "$POSTGRES_USER" \
    "$POSTGRES_DB" | gzip > "$BACKUP_FILE"

SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
echo "[Backup] ✅ Saved: $BACKUP_FILE ($SIZE)"

# Cleanup old backups
find "$BACKUP_DIR" -name "*.sql.gz" -mtime "+$RETENTION_DAYS" -delete
echo "[Backup] Cleaned up backups older than $RETENTION_DAYS days"
echo "[Backup] Done."
