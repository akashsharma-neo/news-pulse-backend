# Seeding tabs and sources (NewsPulse backend)

## Purpose

The UI and API expect `Tab` and `Source` rows in Postgres (`articles` app). Fresh databases (including new Docker volumes) start empty. A management command fills **navigation tabs** and **up to 10 sources per category** so `/api/clusters/tabs/` and `/api/sources/` are useful without manual admin entry.

## Command

```bash
docker compose exec django python manage.py seed_news_catalog
```

Run from the `news-pulse-backend` directory where `docker-compose.yml` lives.

Module: `articles.management.commands.seed_news_catalog`.

## Behaviour (summary)

- **Tabs:** Upserts by `slug`: `india`, `just-for-you`, `sports`, `business`, `global` with display order aligned to the frontend tab bar. **`just-for-you` has no sources** (personalized feed uses other APIs / logic).
- **Sources:** For each real category slug, up to **10** rows: mostly **RSS**, with **web** where `worker.tasks.SCRAPER_CONFIGS` expects it (e.g. Times of India, Moneycontrol, ESPNcricinfo) so in-code URLs and selectors still apply.
- **Idempotent:** Upserts by `(name, category)` so re-running updates URLs and flags instead of duplicating rows.

## Docker image note

Compose bind-mounts **`./worker` only** into the Django container, not `articles/`. The `seed_news_catalog` command ships **inside the image**. After editing the command or related code under `articles/`, rebuild before `exec`:

```bash
docker compose build django && docker compose up -d django
docker compose exec django python manage.py seed_news_catalog
```

## After seeding

Seeding does **not** fetch articles. Next steps (Celery worker + Beat, scrape → cluster → summarize, env vars, verification):

**[celery-pipeline.md](celery-pipeline.md)** — full background ingestion process and how stories appear in the UI.

## RSS URLs

Feed URLs can change or return errors over time; treat the bundled list as **dev / bootstrap** data and adjust sources in Django admin or by editing the command if a feed breaks.
