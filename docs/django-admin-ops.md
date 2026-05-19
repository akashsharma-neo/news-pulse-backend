# Django admin — scrape button and model totals

## What changed

- Every registered admin **changelist** shows a **Total** line with the full row count for that model (unfiltered table count).
- The **Articles** changelist (`/admin/articles/article/`) additionally shows:
  - **Pipeline totals**: Articles, Sources (active / total), Topic clusters, Tabs
  - **Run scrape now** — queues `worker.tasks.scrape_sources` via Celery
  - **Cluster articles now** — queues `worker.tasks.cluster_and_summarize` (groups unclustered articles from the last 48h into `TopicCluster` rows for the feed)
- The **Topic clusters** changelist (`/admin/articles/topiccluster/`) additionally shows:
  - **Summarization** — count of clusters with empty `summary`
  - **Mark pending summaries done** — fills empty summaries from article excerpts (no LLM; sync)
  - **Summarize clusters now (LLM)** — queues `worker.tasks.summarize_clusters` via Celery (hidden when `SUMMARIZE_ENABLED=false`)

## Run scrape from admin

1. Stack must include **django**, **celery**, and **redis** (see `docker-compose.yml`).
2. At least one `Source` must have **active** checked (seed with `python manage.py seed_news_catalog` if empty).
3. Open `/admin/articles/article/` as a staff user and click **Run scrape now**.
4. A success message includes the Celery task id. Monitor in Flower or worker logs (see [celery-pipeline.md](celery-pipeline.md)).

The button runs the same task as Beat (`scrape_sources`): parallel per-source scrapes, then `cluster_and_summarize` when the chord completes. Each scrape also schedules a **debounced** `cluster_and_summarize` (~90s) as a backup if the chord callback is lost.

If queuing fails, confirm the Celery worker is running and `CELERY_BROKER_URL` / Redis are reachable.

## Cluster articles from admin

1. Open `/admin/articles/article/` and check **Unclustered (48h)** in pipeline totals.
2. Click **Cluster articles now** to queue `cluster_and_summarize`.
3. When `SUMMARIZE_ENABLED=true`, new clusters dispatch `summarize_clusters` automatically. Locally (`SUMMARIZE_ENABLED=false`), use **Mark pending summaries done** on the Topic clusters changelist instead of LLM summarization.

Beat must include `cluster-every-hour` in `CELERY_BEAT_SCHEDULE` (`core/settings.py`). After changing the schedule, restart Beat: `docker compose restart celerybeat`.

## Summarize clusters from admin

1. Same stack as scrape: **django**, **celery**, **redis**, and a valid **`OPENAI_COMPATIBLE_API_KEY`** (see [celery-pipeline.md](celery-pipeline.md)).
2. Open `/admin/articles/topiccluster/` and click **Summarize clusters now**.
3. Only clusters with **empty** `summary` are processed. To regenerate short or placeholder summaries, clear `summary` on those rows (or use a one-off shell) and run the button again.

The task fetches full article pages when stored `full_text` is thin, combines related same-tab articles when titles match, and requires LLM output of roughly **60–80 words** (2–3 sentences).

## Counts

| Display | Meaning |
|---------|---------|
| **Total** (all changelists) | `COUNT(*)` on that model’s table |
| **Pipeline totals** (Articles only) | Cross-model snapshot at page load |

Counts are not live-updated after scraping; refresh the page to see new totals.

## Templates and Docker

Shared admin templates live under **`core/templates/admin/`**. The `core` app is in `INSTALLED_APPS` and is bind-mounted in Compose (`./core:/app/core`), so every changelist (Articles, Topic clusters, Sources, Users, etc.) resolves the same template without a separate `templates/` volume.

`docker-compose.yml` uses `x-app-code-volumes` for Django and lists the same app mounts on Celery (including **`sources`**, which was missing before).

After pulling template or Compose changes, restart Django:

```bash
docker compose up -d django
```

Verify templates inside the container:

```bash
docker compose exec django python manage.py shell -c \
  "from django.template.loader import get_template; print(get_template('admin/change_list_with_count.html').origin)"
```

Expected path: `/app/core/templates/admin/change_list_with_count.html`.

## Code locations

- Mixin: `core/admin_mixins.py`
- Shared changelist template: `core/templates/admin/change_list_with_count.html`
- Article admin + scrape view: `articles/admin.py`
- Article-only template: `articles/templates/admin/articles/article/change_list.html`
- Topic cluster admin + summarize view: `articles/admin.py` (`TopicClusterAdmin`)
- Topic cluster template: `articles/templates/admin/articles/topiccluster/change_list.html`
- Scrape/summarize content helpers: `worker/article_content.py`
