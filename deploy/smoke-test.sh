#!/usr/bin/env bash
# Post-deploy smoke checks. Usage: ./deploy/smoke-test.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ -f "${APP_DIR}/.env" ]]; then
	# shellcheck disable=SC1091
	set -a
	source "${APP_DIR}/.env"
	set +a
fi

API_HOST="${CADDY_DOMAIN_API:?set CADDY_DOMAIN_API}"
WWW_HOST="${CADDY_DOMAIN_WWW:?set CADDY_DOMAIN_WWW}"
API_BASE="https://${API_HOST}"
WWW_BASE="https://${WWW_HOST}"

fail=0
check() {
	local name="$1"
	shift
	if "$@"; then
		echo "OK  ${name}"
	else
		echo "FAIL ${name}" >&2
		fail=1
	fi
}

check "API health" curl -fsS "${API_BASE}/health/" -o /dev/null
check "Swagger disabled" bash -c '! curl -fsS "${API_BASE}/api/docs/" -o /dev/null 2>/dev/null'
check "WWW responds" curl -fsS "${WWW_BASE}/" -o /dev/null

if command -v docker &>/dev/null && docker ps --format '{{.Names}}' | grep -q '^np-celery$'; then
	check "Celery ping" docker exec np-celery celery -A core inspect ping --timeout=10
fi

if [[ "$fail" -ne 0 ]]; then
	exit 1
fi
echo "All smoke checks passed."
