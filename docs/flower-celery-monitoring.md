# Flower, Celery Beat, and task visibility

## Why Beat “schedules” do not appear in Flower

Flower monitors **workers and the broker**: running tasks, task history (when events are enabled), queues, and worker controls. **Celery Beat** is a separate process that decides when to enqueue work; Flower does not list your `beat_schedule` / cron definitions as a first-class screen (see [Flower issue #740](https://github.com/mher/flower/issues/740)).

What you should see when Beat is healthy:

- Tasks **after** Beat puts them on the broker (same as manually triggered tasks).
- Broker queue depth if workers are slow or stopped.

For the **schedule definition**, use the codebase (`core/celery.py` merged with `CELERY_BEAT_SCHEDULE` in `core/settings.py`), `celerybeat` logs, or a dedicated Beat observability tool (metrics, Sentry Crons, etc.).

## Task events (Flower timeline / history)

`CELERY_WORKER_SEND_TASK_EVENTS` and `CELERY_TASK_SEND_SENT_EVENT` are enabled in `core/settings.py` so workers emit Celery events Flower can use for a clearer task stream and history. Restart the **worker** (and Flower if it was already running) after changing settings.

## Triggering tasks manually

1. **Flower HTTP API** (with Docker Compose basic auth: `FLOWER_USER` / `FLOWER_PASS`, default `admin` / `admin`):

   - Async (returns task id): `POST http://127.0.0.1:5555/api/task/async-apply/<task_name>`  
     JSON body: `{"args":[],"kwargs":{},"options":{}}`  
     Example task name: `worker.tasks.scrape_sources`
   - Same pattern for `apply` (wait for result) and `send-task`; see [Flower API — task endpoints](https://flower.readthedocs.io/en/latest/api.html).

2. **Shell inside the stack**:

   ```bash
   docker compose exec django python manage.py shell -c "from worker.tasks import scrape_sources; scrape_sources.delay()"
   ```

3. **Celery CLI** (from a container that has the app and broker env):

   ```bash
   celery -A core call worker.tasks.scrape_sources
   ```

## Beat schedule merge (fix)

Previously, `core/celery.py` replaced `app.conf.beat_schedule` after loading Django settings, which **dropped** entries from `CELERY_BEAT_SCHEDULE` (e.g. digest tasks). The app now **merges** settings-defined entries with the worker periodic tasks defined in code.

## Optional: more “powers” in Flower

- **Prometheus**: Flower can expose metrics; see [Flower features](https://flower.readthedocs.io/en/latest/features.html).
- **OAuth**: Flower supports Google/GitHub/GitLab/Okta instead of only `--basic_auth`.
- **Broker API**: Some broker management features expect `--broker_api` (most relevant for RabbitMQ; this project uses Redis).
