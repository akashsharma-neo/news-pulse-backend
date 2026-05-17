#!/usr/bin/env bash
# Pull ECR images and restart the production stack. Run from /opt/newspulse.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "$APP_DIR"

if [[ ! -f .env ]]; then
	echo "Missing .env in ${APP_DIR}. Copy config/env/prod.example and prod.deploy.example." >&2
	exit 1
fi

# shellcheck disable=SC1091
set -a
source .env
set +a

: "${AWS_REGION:?set AWS_REGION in .env}"
: "${ECR_API_IMAGE:?set ECR_API_IMAGE in .env}"
: "${ECR_WEB_IMAGE:?set ECR_WEB_IMAGE in .env}"

echo "==> ECR login (${AWS_REGION})..."
aws ecr get-login-password --region "$AWS_REGION" \
	| docker login --username AWS --password-stdin "${ECR_API_IMAGE%%/*}"

echo "==> Pulling images..."
docker compose -f docker-compose.prod.yml pull

echo "==> Starting stack..."
docker compose -f docker-compose.prod.yml up -d

echo "==> Running migrations..."
docker exec np-django python manage.py migrate --noinput

echo "Deploy finished. Health: curl -fsS https://${CADDY_DOMAIN_API}/health/"
