# NewsPulse backend — operational docs

Guides for running and deploying this Django API.

- [environments.md](environments.md) — `NEWSMINE_ENV` profiles (dev LM Studio, staging/prod via `.env`).
- [production-security.md](production-security.md) — prod checklist, API hardening, LAN vs public deploy.
- [static-files-docker.md](static-files-docker.md) — serving `/static/` (admin, DRF, Swagger) in Docker with Gunicorn.
- [seed-tabs-and-sources.md](seed-tabs-and-sources.md) — populating category tabs and RSS/web sources for scraping.
- [celery-pipeline.md](celery-pipeline.md) — scrape → cluster → summarize pipeline, Beat schedule, and troubleshooting.
- [flower-celery-monitoring.md](flower-celery-monitoring.md) — Flower vs Beat, task events, and triggering tasks.
- [article-chat.md](article-chat.md) — article-detail AI chat API, OpenRouter env, and verification.
