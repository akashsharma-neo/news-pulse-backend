#!/usr/bin/env bash
# Install daily pg_dump cron → S3. Run on EC2 as root after stack is up.
# Requires: BACKUP_S3_URI=s3://bucket/path/ in .env or environment.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/newspulse}"
BACKUP_S3_URI="${BACKUP_S3_URI:?set BACKUP_S3_URI e.g. s3://my-bucket/newspulse-backups}"
CRON_SCHEDULE="${CRON_SCHEDULE:-0 3 * * *}"

DUMP_SCRIPT="${APP_DIR}/deploy/pg-dump-s3.sh"
chmod +x "$DUMP_SCRIPT"

CRON_LINE="${CRON_SCHEDULE} ${DUMP_SCRIPT} >> /var/log/newspulse-pg-backup.log 2>&1"
( crontab -l 2>/dev/null | grep -v 'pg-dump-s3.sh' || true; echo "$CRON_LINE" ) | crontab -
echo "Installed cron: ${CRON_LINE}"
