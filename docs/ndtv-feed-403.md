# NDTV RSS fetch failures (403)

## Symptom

Celery worker logs show `scrape_source` retries then fail:

```text
Exception: Failed to fetch https://feeds.ndtv.com/ndtv/index.xml
```

`_fetch_page` returns `None` when the HTTP client gets a **4xx** (except 408/429). NDTV’s `feeds.ndtv.com` host often responds with **403 Forbidden** to datacenter IPs and non-browser user agents.

## Fix (in repo)

- **Scraper config** (`worker/tasks.py`): NDTV uses Feedburner India news  
  `https://feeds.feedburner.com/ndtvnews-india-news`
- **Default fetch headers**: Mozilla-compatible `User-Agent` and `Accept` for RSS/HTML.
- **Seed catalog** (`seed_news_catalog`): same Feedburner URL for new DBs.

`scrape_source` resolves the URL from `SCRAPER_CONFIGS` by **source name**, so workers pick up the new URL without changing the `Source` row — as long as the source is named exactly `NDTV`.

## Existing databases

If you created sources before this change and the name is not in `SCRAPER_CONFIGS`, update the row:

```bash
docker compose exec django python manage.py shell -c "
from articles.models import Source
Source.objects.filter(name='NDTV').update(
    url='https://feeds.feedburner.com/ndtvnews-india-news'
)
"
```

## Verify

```bash
docker compose exec worker celery -A core call worker.tasks.scrape_source --args='[<NDTV_SOURCE_ID>]'
```

Or re-run the full scrape from Django admin (**Run scrape now**).

Check worker logs for `Scraping source: NDTV` and a non-zero `fetched` count.
