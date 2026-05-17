#!/usr/bin/env bash
# Bootstrap Amazon Linux 2023 (ARM) for NewsPulse production.
# Run as root on a fresh EC2 instance (SSM or SSH).
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/newspulse}"
APP_USER="${APP_USER:-ec2-user}"

echo "==> Installing Docker, Compose plugin, AWS CLI, SSM agent..."
dnf update -y
dnf install -y docker git amazon-ssm-agent
systemctl enable --now docker
systemctl enable --now amazon-ssm-agent

if ! docker compose version &>/dev/null; then
	dnf install -y docker-compose-plugin 2>/dev/null || true
fi
if ! docker compose version &>/dev/null; then
	mkdir -p /usr/local/lib/docker/cli-plugins
	curl -fsSL "https://github.com/docker/compose/releases/latest/download/docker-compose-linux-aarch64" \
		-o /usr/local/lib/docker/cli-plugins/docker-compose
	chmod +x /usr/local/lib/docker/cli-plugins/docker-compose
fi

if ! command -v aws &>/dev/null; then
	curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-aarch64.zip" -o /tmp/awscliv2.zip
	unzip -q /tmp/awscliv2.zip -d /tmp
	/tmp/aws/install
	rm -rf /tmp/aws /tmp/awscliv2.zip
fi

usermod -aG docker "$APP_USER" || true

echo "==> Creating app directory ${APP_DIR}..."
mkdir -p "$APP_DIR"
chown "$APP_USER:$APP_USER" "$APP_DIR"

cat <<EOF

Bootstrap complete.

Next steps (as ${APP_USER}):
  1. Clone or sync the backend repo into ${APP_DIR} (docker-compose.prod.yml, deploy/, docker/postgres/).
  2. Copy config/env/prod.example to ${APP_DIR}/.env and fill all values.
  3. Set ECR_API_IMAGE, ECR_WEB_IMAGE, CADDY_DOMAIN_WWW, CADDY_DOMAIN_API.
  4. Run: ${APP_DIR}/deploy/deploy.sh

EOF
