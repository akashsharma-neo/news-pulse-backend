# Article and cluster images

## What changed

- **`Article.source_image_url`** — publisher lead image URL from RSS (`media_thumbnail`, `media_content`, summary `<img>`) or web listing scrape.
- **`TopicCluster.image_url`** — display URL chosen at cluster creation (primary article first, then siblings, else tab placeholder).
- **API** — `image_url` on cluster list/detail; `source_image_url` on articles.
- **Frontend** — feed cards and article detail show lead images via `StoryImage`.
- **Placeholders** — bundled under `articles/static/newspulse/placeholders/`; served at `/static/newspulse/placeholders/` in dev.

Scraped images are **hotlinked** (publisher CDN URLs). Only placeholder assets use our staticfiles / S3 prefix.

## Resolution order (API `image_url`)

1. `TopicCluster.image_url` (if set at cluster time)
2. `primary_article.source_image_url`
3. Tab placeholder (`india.jpg`, `sports.jpg`, …)

## Environment

| Variable | When | Purpose |
|----------|------|---------|
| `BASE_URL` | dev | Builds placeholder URLs when `PLACEHOLDER_BASE_URL` is unset |
| `PLACEHOLDER_BASE_URL` | prod/staging | S3 or CloudFront prefix, e.g. `https://bucket.s3.region.amazonaws.com/newspulse/placeholders` |

Prod example in `config/env/prod.example`.

## Prod: upload placeholders to S3

```bash
aws s3 sync articles/static/newspulse/placeholders/ \
  s3://YOUR_BUCKET/newspulse/placeholders/ \
  --content-type image/jpeg
```

Set `PLACEHOLDER_BASE_URL` to the public URL of that prefix.

## Verify

```bash
docker compose build django celery celerybeat
docker compose up -d
docker compose exec django python manage.py migrate
docker compose exec django python manage.py backfill_cluster_images
curl -s 'http://127.0.0.1:8000/api/clusters/?tab=global&page_size=3' | python -m json.tool
```

Check `results[].image_url` in the JSON. Rebuild Django image after changes under `articles/` (not bind-mounted in compose).

## Backfill existing clusters

```bash
docker compose exec django python manage.py backfill_cluster_images
docker compose exec django python manage.py backfill_cluster_images --all --dry-run
```

Does not re-fetch RSS; only uses stored `source_image_url` or placeholders.
