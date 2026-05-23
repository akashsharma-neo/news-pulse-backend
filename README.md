# NewsMine backend

Django REST API, Celery workers, and Docker Compose stack for the NewsMine service.

**Documentation:** [docs/README.md](docs/README.md) (product backlog, design, frontend theme, runbooks)

| Topic | Doc |
|-------|-----|
| **Background news ingestion (scrape → cluster → feed)** | [docs/celery-pipeline.md](docs/celery-pipeline.md) |
| Environment variables (LLM / DB) | [.env.example](.env.example) |
| Seed tabs & RSS sources | [docs/seed-tabs-and-sources.md](docs/seed-tabs-and-sources.md) |
| Celery / Flower monitoring | [docs/flower-celery-monitoring.md](docs/flower-celery-monitoring.md) |
| Metabase (SQL dashboards) | [docs/metabase.md](docs/metabase.md) |
| Static files in Docker | [docs/static-files-docker.md](docs/static-files-docker.md) |
