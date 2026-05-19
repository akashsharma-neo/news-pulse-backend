# Cluster summaries and article bodies

How NewsPulse builds **100–120 word** cluster digests for the detail page, stores clean article text, and links all articles in a story cluster.

## Data model

- **`Article.full_text`** — plain-text body from RSS and/or article-page fetch (cleaned, up to ~8000 chars).
- **`Article.topic_cluster`** — FK set when clustering groups articles; all members of a story point at the same `TopicCluster`.
- **`TopicCluster.summary`** — unified digest shown on the detail page (LLM or excerpt fallback).

Feed cards still show a **~60 word** client-side preview; detail shows the full cluster summary.

## Pipeline flow

1. **`scrape_source`** — RSS/listing text → optional detail fetch for thin bodies → `clean_article_text` → save `Article`.
2. **`cluster_and_summarize`** — group unclustered articles (`topic_cluster IS NULL`), create `TopicCluster` **or merge into a recent matching cluster in the same tab**, set `topic_cluster` on every member. See [feed-dedup.md](feed-dedup.md).
3. **`summarize_clusters`** — gather primary + up to 4 member `full_text` rows → OpenAI (100–120 words) or sentence-boundary excerpt for single-source clusters.

## Text cleaning (The Hindu and paywalls)

[`worker/article_content.py`](../worker/article_content.py):

- **`clean_article_text`** — strips HTML and login/subscribe boilerplate.
- **`is_usable_article_body`** — rejects junk-heavy text before using it as the main single-source excerpt.
- **The Hindu** `SCRAPER_CONFIGS` entry uses article-body selectors, excludes paywall nodes, and sets `prefer_rss_body: true` so a good RSS deck is not replaced by a login wall from the article page.

## API

- **`GET /api/clusters/{id}/`** — full summary + `primary_url` (for “More at source”).
- **`GET /api/clusters/{id}/related/?limit=8`** — recent clusters in the same tab (detail “More news”).

## Management commands

```bash
# Link existing clusters to member articles (best-effort title match)
python manage.py backfill_cluster_membership
python manage.py backfill_cluster_membership --dry-run

# Re-clean stored bodies (optionally one source)
python manage.py reclean_article_bodies --source "The Hindu"
python manage.py reclean_article_bodies --resummarize

# Fill empty summaries from article text without LLM (admin alternative)
python manage.py mark_clusters_summarized

# One-time local cleanup — keep only today's articles and clusters
python manage.py prune_stale_content
python manage.py prune_stale_content --dry-run
```

`prune_stale_content` deletes clusters with `created_at` before the cutoff, then articles with `fetched_at` before the cutoff **except** articles still linked to a cluster on or after the cutoff (avoids CASCADE dropping newer clusters when the primary article is older).

After deploy, for existing data:

1. `python manage.py migrate`
2. `python manage.py backfill_cluster_membership`
3. `python manage.py reclean_article_bodies --source "The Hindu" --resummarize`
4. Or use Django admin **Summarize clusters** to queue LLM for empty summaries.

## Settings

| Variable | Default | Purpose |
|----------|---------|---------|
| `SUMMARIZE_ENABLED` | `true` (`false` in dev profile) | When false, Beat and clustering skip LLM; use admin or `mark_clusters_summarized` |
| `SUMMARIZE_MAX_TOKENS` | `250` | Headroom for 100–120 word digests |
| `SUMMARIZE_FETCH_FULL_BODY` | `false` | Re-fetch thin bodies at summarize time |

## Verify

1. Detail page: summary ~100–120 words, **More at {source}** opens publisher URL.
2. Hindu stories: no HTML tags or “Subscribe to continue reading” in summary.
3. Multi-source cluster: admin shows multiple sources; summary reflects combined coverage.
4. `GET /api/clusters/{id}/related/` returns same-tab stories excluding current.
