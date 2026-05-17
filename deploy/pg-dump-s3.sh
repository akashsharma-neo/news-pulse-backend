#!/usr/bin/env bash
# Dump Postgres from np-postgres and upload to S3.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/newspulse}"
BACKUP_S3_URI="${BACKUP_S3_URI:?set BACKUP_S3_URI}"
AWS_REGION="${AWS_REGION:-ap-south-1}"

if [[ -f "${APP_DIR}/.env" ]]; then
	# shellcheck disable=SC1091
	set -a
	source "${APP_DIR}/.env"
	set +a
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FILE="/tmp/newspulse-${STAMP}.sql.gz"

docker exec np-postgres pg_dump -U "${POSTGRES_USER}" "${POSTGRES_DB}" | gzip > "$FILE"
aws s3 cp "$FILE" "${BACKUP_S3_URI}/newspulse-${STAMP}.sql.gz" --region "$AWS_REGION"
rm -f "$FILE"

# Keep last 7 days (best-effort; requires s3:ListBucket + s3:DeleteObject on prefix)
PREFIX="${BACKUP_S3_URI#s3://}"
BUCKET="${PREFIX%%/*}"
KEY_PREFIX="${PREFIX#*/}"
aws s3 ls "s3://${BUCKET}/${KEY_PREFIX}/" --region "$AWS_REGION" \
	| awk '{print $4}' | sort | head -n -7 | while read -r old; do
	[[ -n "$old" ]] && aws s3 rm "s3://${BUCKET}/${KEY_PREFIX}/${old}" --region "$AWS_REGION" || true
	done

echo "Backup uploaded: ${BACKUP_S3_URI}/newspulse-${STAMP}.sql.gz"
