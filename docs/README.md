# NewsMine / NewsPulse documentation

All project documentation for the NewsMine workspace lives in this directory (versioned with the Django API repo).

## Product and design

- [product-backlog.md](product-backlog.md) — features, UX, and planning (single backlog)
- [design.md](design.md) — product concept and architecture (draft)
- [frontend-theme.md](frontend-theme.md) — Next.js default dark theme tokens

## Development reference

- [AGENTS.md](AGENTS.md) — Next.js agent rules and backend test conventions

## Local dev hostname

When your LAN IP changes, set **`NEWSMINE_DEV_HOST`** once (prefer `YourMac.local` for phone testing). Run [`../../scripts/dev-host.sh`](../../scripts/dev-host.sh) and see [environments.md](environments.md#dev-hostname-newsmine_dev_host).

## Backend operations

- [environments.md](environments.md) — `NEWSMINE_ENV` profiles (dev LM Studio, staging/prod via `.env`), `NEWSMINE_DEV_HOST` for LAN/phone.
- [production-security.md](production-security.md) — prod checklist, API hardening, LAN vs public deploy.
- [aws-deployment.md](aws-deployment.md) — AWS infra plan (~100 users): EC2 + Compose + ECR, cost, scaling path, [deploy cheatsheet](aws-deployment.md#deploy-cheatsheet-logs--debugging).
- [github-actions-ecr.md](github-actions-ecr.md) — CI build/push to ECR on merge to `main` (dev → PR → main), GitHub secrets setup.
- [docker-images.md](docker-images.md) — slim API image vs optional embeddings image (no CUDA in prod).
- [deploy/README.md](../deploy/README.md) — production scripts: bootstrap, ECR deploy, Cloudflare/SES, smoke tests.
- [static-files-docker.md](static-files-docker.md) — serving `/static/` (admin, DRF, Swagger) in Docker with Gunicorn.
- [seed-tabs-and-sources.md](seed-tabs-and-sources.md) — populating category tabs and RSS/web sources for scraping.
- [celery-pipeline.md](celery-pipeline.md) — scrape → cluster → summarize pipeline, Beat schedule, and troubleshooting.
- [ndtv-feed-403.md](ndtv-feed-403.md) — NDTV RSS 403 / `Failed to fetch feeds.ndtv.com`, Feedburner URL fix.
- [cluster-summaries.md](cluster-summaries.md) — 100–120 word digests, cluster membership, text cleaning, related API, backfill commands.
- [feed-dedup.md](feed-dedup.md) — duplicate stories on the tab feed, URL normalization, `dedupe_topic_clusters`.
- [django-admin-ops.md](django-admin-ops.md) — admin changelist totals, scrape/cluster actions, **Mark pending summaries done** (local, no LLM).
- [flower-celery-monitoring.md](flower-celery-monitoring.md) — Flower vs Beat, task events, and triggering tasks.
- [metabase.md](metabase.md) — Metabase UI for exploring Postgres data in Docker.
- [article-chat.md](article-chat.md) — Nex article-detail chat API, suggested questions, OpenRouter env, and verification.
- [auth.md](auth.md) — User login: email verification, Firebase Google/phone OTP, JWT API, env setup.
- [article-images.md](article-images.md) — scrape images, cluster display URLs, placeholders, and S3.
