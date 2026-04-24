#!/bin/bash
# SchoolAI — backup automático de PostgreSQL
# Ejecutado por systemd timer diariamente.
# Retiene los últimos 7 dumps en ~/schoolai/backups/auto/

set -euo pipefail

BACKUP_DIR="$HOME/schoolai/backups/auto"
DB_CONTAINER="schoolai-db"
DB_NAME="schoolai"
DB_USER="schoolai"
DB_PASS="1234"
KEEP_DAYS=7

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
OUTFILE="$BACKUP_DIR/schoolai_${TIMESTAMP}.dump"

docker exec -e PGPASSWORD="$DB_PASS" "$DB_CONTAINER" \
    pg_dump -U "$DB_USER" -F c "$DB_NAME" > "$OUTFILE"

SIZE=$(du -h "$OUTFILE" | cut -f1)
echo "[$(date)] Backup creado: $OUTFILE ($SIZE)"

# Eliminar backups más viejos que KEEP_DAYS días
find "$BACKUP_DIR" -name "*.dump" -mtime "+$KEEP_DAYS" -delete
echo "[$(date)] Limpieza: backups > ${KEEP_DAYS} días eliminados."
