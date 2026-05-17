# NewsPulse backend — operational docs

Guides for running and deploying this Django API.

- [environments.md](environments.md) — `NEWSMINE_ENV` profiles (dev LM Studio, staging/prod via `.env`), `NEWSMINE_DEV_HOST` for LAN/phone.
- [production-security.md](production-security.md) — prod checklist, API hardening, LAN vs public deploy.
- [aws-deployment.md](aws-deployment.md) — AWS infra plan (~100 users): EC2 + Compose + ECR, cost, scaling path.
- [static-files-docker.md](static-files-docker.md) — serving `/static/` (admin, DRF, Swagger) in Docker with Gunicorn.
- [seed-tabs-and-sources.md](seed-tabs-and-sources.md) — populating category tabs and RSS/web sources for scraping.
- [celery-pipeline.md](celery-pipeline.md) — scrape → cluster → summarize pipeline, Beat schedule, and troubleshooting.
- [django-admin-ops.md](django-admin-ops.md) — admin changelist totals, **Run scrape now**, and **Summarize clusters now**.
- [flower-celery-monitoring.md](flower-celery-monitoring.md) — Flower vs Beat, task events, and triggering tasks.
- [metabase.md](metabase.md) — Metabase UI for exploring Postgres data in Docker.
- [article-chat.md](article-chat.md) — article-detail AI chat API, OpenRouter env, and verification.
- [article-images.md](article-images.md) — scrape images, cluster display URLs, placeholders, and S3.
