#!/bin/bash
# Phoenix Bot Database Backup Script
# Runs hourly via cron
# Retains 30 days of backups

BACKUP_DIR="/opt/phoenix-bot/backups"
DB_PATH="/opt/phoenix-bot/data/phoenix_bot.db"
RETENTION_DAYS=30

# Create backup directory if it doesn't exist
mkdir -p "$BACKUP_DIR"

# Generate timestamp
TIMESTAMP=$(date +%Y%m%d_%H%M)
BACKUP_FILE="$BACKUP_DIR/db_${TIMESTAMP}.db.gz"

# Create compressed backup
gzip -c "$DB_PATH" > "$BACKUP_FILE"

# Log success
echo "$(date): Backup created: $BACKUP_FILE" >> "$BACKUP_DIR/backup.log"

# Delete backups older than retention period
find "$BACKUP_DIR" -name "db_*.db.gz" -type f -mtime +$RETENTION_DAYS -delete

# Log cleanup
echo "$(date): Old backups cleaned (retention: ${RETENTION_DAYS} days)" >> "$BACKUP_DIR/backup.log"
