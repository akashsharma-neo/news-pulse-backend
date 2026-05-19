# NewsPulse production deploy

Scripts and config for [AWS deployment](../docs/aws-deployment.md) (EC2 + Compose + ECR + Cloudflare).

**Day-2 ops:** [Deploy cheatsheet](../docs/aws-deployment.md#deploy-cheatsheet-logs--debugging) — logs, health checks, Celery, common failures.

## Quick path

| Step | Action |
|------|--------|
| 1 | `docker-compose.prod.yml` + this folder on EC2 at `/opt/newspulse` |
| 2 | `./deploy/bootstrap-ec2.sh` (as root on fresh AL2023 ARM instance, `t4g.small`) |
| 3 | GitHub Actions push images (see below) |
| 4 | `./deploy/aws-foundation.sh` (ECR, SG, IAM; then launch EC2 + Elastic IP) |
| 5 | Cloudflare + SES — [cloudflare-ses.md](cloudflare-ses.md) |
| 6 | `.env` from `config/env/prod.example` + `prod.deploy.example`, then `./deploy/deploy.sh` |
| 7 | `./deploy/smoke-test.sh`, backup cron, CloudWatch alarm |

## GitHub Actions

**Branch flow:** work on `dev` → PR to `main` → **merge** triggers ECR build (push to `main` only; not on `dev`).

**Setup (one-time):** [github-actions-ecr.md](../docs/github-actions-ecr.md) — IAM user, secrets, variables, first merge.

| Repo | Workflow | Image |
|------|----------|--------|
| Backend | `.github/workflows/deploy-ecr.yml` | `newspulse-api` (linux/arm64) |
| Frontend | `.github/workflows/deploy-ecr.yml` | `newspulse-web` (linux/arm64) |

**Secrets** (both repos): `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`

**Variables** (frontend): `NEXT_PUBLIC_API_URL` = `https://api.yourdomain.com/api`  
**Variables** (optional both): `AWS_REGION` = `ap-south-1`

**Optional** (backend): `deploy-ssm.yml` — workflow_dispatch with `instance_id` to run `deploy.sh` via SSM.

## Cloudflare TLS

- DNS: proxied `www` and `api` → Elastic IP
- SSL/TLS mode: **Full (strict)**
- Origin: Caddy on EC2 obtains Let's Encrypt certs for `CADDY_DOMAIN_WWW` and `CADDY_DOMAIN_API`

## Files

| File | Purpose |
|------|---------|
| `Caddyfile` | Route www → frontend, api → django |
| `bootstrap-ec2.sh` | Docker, Compose, AWS CLI, SSM |
| `aws-foundation.sh` | ECR repos, security group, IAM instance profile |
| `deploy.sh` | ECR login, pull, up, migrate |
| `smoke-test.sh` | Health, Swagger off, WWW, Celery ping |
| `pg-dump-s3.sh` | Postgres backup to S3 |
| `setup-backup-cron.sh` | Daily cron for backups |
| `setup-cloudwatch-alarm.sh` | CPU > 80% alarm |
| `cloudflare-ses.md` | DNS, SES, `.env` checklist |
