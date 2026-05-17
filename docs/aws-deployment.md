# AWS deployment (first ~100 users)

Infrastructure plan for running NewsPulse in production on AWS at low cost. Target: **~$16–20/month** on `t4g.small` (excluding LLM API usage).

**Approach:** one **`t4g.small` EC2** instance (ARM) running **Docker Compose (prod)** + **ECR** for images + **TLS reverse proxy** (Cloudflare or Caddy). Skip EKS, ALB, RDS, and ElastiCache until you outgrow this box.

Related docs:

- [production-security.md](production-security.md) — prod env checklist, CORS, TLS headers, rate limits
- [environments.md](environments.md) — `NEWSMINE_ENV` and `.env` templates
- [config/env/prod.example](../config/env/prod.example) — production variable template

---

## Summary

| Decision | Choice |
|----------|--------|
| Compute | Single EC2 `t4g.small` (ARM, 2 GiB RAM; `EMBEDDINGS_ENABLED=false`) |
| Orchestration | Docker Compose (prod overlay, not dev bind-mounts) |
| Images | ECR (`newspulse-api`, `newspulse-web`) |
| Database | Postgres 17 + pgvector on the same instance |
| Cache / broker | Redis on the same instance |
| TLS | Cloudflare (free) **or** Caddy + Let's Encrypt on EC2 |
| Email | Amazon SES SMTP |
| **Not used yet** | EKS, ECS Fargate, ALB, RDS, ElastiCache, API Gateway |

---

## Architecture

```mermaid
flowchart TB
  user[Browser]
  cf[Cloudflare_TLS_optional]
  ec2[EC2_t4g_small]
  proxy[Caddy_or_Nginx]
  next[Next.js_container]
  django[Django_Gunicorn]
  celery[Celery_worker_plus_beat]
  pg[(Postgres_pgvector)]
  redis[(Redis)]
  ecr[ECR_images]
  llm[OpenAI_compatible_API]
  smtp[SES_SMTP]

  user --> cf --> proxy
  cf --> ec2
  proxy --> next
  proxy --> django
  next -->|HTTPS_api_host| django
  django --> pg
  django --> redis
  celery --> pg
  celery --> redis
  celery --> llm
  celery --> smtp
  ecr -.->|pull_on_deploy| ec2
```

**Hostnames (example):**

- `https://www.yourdomain.com` → Next.js (`frontend:3000`)
- `https://api.yourdomain.com` → Django Gunicorn (`django:8000`)
- Health: `GET https://api.yourdomain.com/health/`

The browser calls the API on the **public API hostname** (`NEXT_PUBLIC_API_URL`), not Docker internal names.

---

## Why not EKS / serverless / API Gateway (for now)

| Option | Verdict |
|--------|---------|
| **EKS** | ~$73/mo control plane alone + nodes; heavy ops. Overkill for ~100 users. |
| **Lambda + API Gateway** | Poor fit: long-running Celery, beat schedules, local PyTorch embeddings in the API image. |
| **App Runner** | OK for one web container; still need an always-on Celery worker + model cache volume. |
| **ECS Fargate + RDS + ALB** | Good **phase 2** (~$90–130/mo). Use after validating on a single box. |

**ECR** is still recommended: push pre-built images from CI instead of compiling PyTorch on the instance.

**API Gateway:** skip initially. Terminate TLS at Cloudflare or Caddy; Django already applies per-IP/user rate limits (see [production-security.md](production-security.md)).

---

## Services on the box

| Compose service | Production | Notes |
|-----------------|------------|-------|
| `django` | Yes | Expose only via reverse proxy |
| `frontend` | Yes | Build with prod `NEXT_PUBLIC_*` (see below) |
| `celery` | Yes | Needs ~2 GiB+ free RAM for `sentence-transformers` |
| `celerybeat` | Yes | Exactly one beat instance |
| `postgres` | Yes | pgvector via [docker/postgres/init-pgvector.sql](../docker/postgres/init-pgvector.sql) |
| `redis` | Yes | Celery broker + Django cache |
| `flower` | No | Do not expose to the internet (or VPN-only) |
| `metabase` | No | Saves ~512MB–1GB RAM; use later if needed |

Base reference: [docker-compose.yml](../docker-compose.yml) (dev). Production needs a separate **`docker-compose.prod.yml`** (not in repo yet — see checklist below).

---

## Instance and networking

### EC2

- **Type (default):** `t4g.small` (2 vCPU, 2 GiB), e.g. `ap-south-1` (Mumbai) — fits scrape + cluster + summarize with `EMBEDDINGS_ENABLED=false` (default).
- **With embeddings:** upgrade to `t4g.medium` (4 GiB) or run `celery-embeddings` on a separate instance/profile.
- **Disk:** 30–40 GiB gp3 root (Postgres + `model_cache` for Hugging Face model)
- **Elastic IP:** stable DNS target (small charge if instance is stopped)

### Security group

| Port | Access |
|------|--------|
| 22 | Your IP only, **or** disable SSH and use SSM Session Manager |
| 80, 443 | `0.0.0.0/0` (or Cloudflare IP ranges if proxied) |
| 5432, 6379, 3000, 8000, 5555 | **Not** public |

### VPC

Default VPC + public subnet is fine for a first deploy.

### TLS (pick one)

**A — Cloudflare (simplest, $0):** Proxy `www` and `api` to the EC2 IP; SSL mode “Full (strict)”; origin serves HTTPS (Caddy/Nginx + origin cert).

**B — Caddy on EC2:** Automatic Let's Encrypt for both hostnames; no ALB.

Proxy must send `X-Forwarded-Proto: https` and correct `Host` for Django `SECURE_SSL_REDIRECT` (see [production-security.md](production-security.md)).

---

## ECR and deploy flow

```mermaid
sequenceDiagram
  participant GH as GitHub_Actions
  participant ECR as ECR
  participant EC2 as EC2
  GH->>ECR: build_push django_image
  GH->>ECR: build_push frontend_image
  GH->>EC2: SSM_run_deploy_script
  EC2->>ECR: docker_pull
  EC2->>EC2: docker_compose_up_prod
```

1. **ECR repositories:** `newspulse-api`, `newspulse-web` (tags: git `sha` + `latest`)
2. **Build frontend in CI** with:
   - `NEXT_PUBLIC_NEWSMINE_ENV=prod`
   - `NEXT_PUBLIC_API_URL=https://api.yourdomain.com/api`
3. **EC2 IAM role:** `ecr:GetAuthorizationToken`, `ecr:BatchGetImage`, `ssm:UpdateInstanceInformation`
4. **Deploy on instance:**
   ```bash
   aws ecr get-login-password --region <region> | docker login ...
   docker compose -f docker-compose.prod.yml pull
   docker compose -f docker-compose.prod.yml up -d
   docker exec np-django python manage.py migrate
   ```

Frontend image must be rebuilt whenever `NEXT_PUBLIC_*` changes.

---

## Production environment

Copy [config/env/prod.example](../config/env/prod.example) to `.env` on the server (never commit).

| Variable | Example |
|----------|---------|
| `NEWSMINE_ENV` | `prod` |
| `DJANGO_ALLOWED_HOSTS` | `api.yourdomain.com` |
| `CORS_ALLOWED_ORIGINS` | `https://www.yourdomain.com` |
| `BASE_URL` | `https://api.yourdomain.com` |
| `NEXT_PUBLIC_API_URL` | `https://api.yourdomain.com/api` (build-time for frontend image) |
| `DATABASE_HOST` | `postgres` (compose service name) |
| `CELERY_BROKER_URL` | `redis://redis:6379/0` |
| `REDIS_URL` | `redis://redis:6379/1` |
| `OPENAI_COMPATIBLE_*` | Hosted API (OpenRouter, etc.) — not `host.docker.internal` |
| `EMAIL_*` | Amazon SES SMTP credentials |

Full checklist: [production-security.md](production-security.md).

---

## AWS services checklist

| Service | Use |
|---------|-----|
| EC2 `t4g.small` | Full stack (no local embeddings) |
| ECR | API + web images |
| Elastic IP | Stable DNS |
| Route53 | Optional hosted zone (~$0.50/mo) |
| SES | Digest / auth email |
| S3 | Optional tab placeholder images (`PLACEHOLDER_BASE_URL` in prod.example) |
| Secrets Manager | Optional instead of plain `.env` on disk |
| CloudWatch | CPU/disk alarms; container logs |

**Defer:** EKS, ALB (~$16/mo fixed), RDS, ElastiCache, API Gateway, WAF.

---

## Monthly cost estimate (`ap-south-1`, Mumbai)

| Item | ~USD/mo |
|------|---------|
| `t4g.small` | ~12 |
| 40 GiB gp3 | 3 |
| ECR (2 images) | 1–2 |
| SES (low volume) | 0 |
| Cloudflare | 0 |
| **Infra subtotal** | **~16–20** |
| LLM API (OpenRouter, etc.) | usage-based |

---

## Operational notes

1. **Embeddings (optional):** disabled by default (`EMBEDDINGS_ENABLED=false`). To backfill vectors, set `EMBEDDINGS_ENABLED=true` and start the compose profile: `docker compose --profile embeddings up -d celery-embeddings`. First run downloads the model into `model_cache` (`EMBEDDING_MODEL_PATH=/data/embeddings-models`); avoid multiple embed workers on 4 GiB RAM.
2. **Celery beat:** run a single `celerybeat` container.
3. **Post-deploy checks:** Swagger 404, CORS preflight, `/health/`, no public Postgres/Redis — see [production-security.md](production-security.md).
4. **Backups:** daily `pg_dump` to S3 via cron, or weekly EBS snapshots; retain ~7 days and test a restore once.

---

## Scaling path (when to leave the single box)

Migrate incrementally (~500+ users or HA needs):

1. **RDS PostgreSQL** (pgvector) — data off the instance
2. **ElastiCache Redis** — broker/cache managed
3. **ECS Fargate + one ALB** — host rules for `api` / `www`; still skip EKS until you need Kubernetes-specific tooling

---

## Implementation checklist

Repo artifacts (run on EC2 / in CI):

- [x] `docker-compose.prod.yml` — ECR images, Caddy, no Flower/Metabase, internal DB/Redis
- [x] `deploy/Caddyfile` — hostname routing, forwarded headers
- [x] `deploy/bootstrap-ec2.sh` — Docker, Compose v2, AWS CLI, SSM agent
- [x] GitHub Actions — [`.github/workflows/deploy-ecr.yml`](../.github/workflows/deploy-ecr.yml) (API); frontend repo has web workflow
- [x] `deploy/aws-foundation.sh` — ECR repos, security group, IAM instance profile (run locally with AWS CLI)
- [x] `deploy/cloudflare-ses.md` — DNS + SES + `.env` checklist
- [x] `deploy/deploy.sh` — pull, up, migrate
- [x] `deploy/smoke-test.sh` — health, Swagger off, Celery ping
- [x] `deploy/pg-dump-s3.sh` + `setup-backup-cron.sh` + `setup-cloudwatch-alarm.sh`
- [x] Optional SSM deploy — [`.github/workflows/deploy-ssm.yml`](../.github/workflows/deploy-ssm.yml)

**You still run manually:** launch EC2 + Elastic IP, point Cloudflare, fill `.env`, first `createsuperuser`, seed, and smoke test in the browser.

See [deploy/README.md](../deploy/README.md) for the step-by-step runbook.
