# Feed duplicate stories

## Symptom

The tab feed (`/api/clusters/`) shows the **same story twice** (similar headline, different cluster IDs).

## Root causes

1. **Clustering only looked at unclustered articles** — each scrape run created a **new** `TopicCluster` even when an older cluster in the same tab already covered that story.
2. **Article URL dedup was exact-string** — `https://…/story` vs `https://www.…/story/?utm_source=x` created two `Article` rows and two clusters.

## Fixes (code)

- **`articles/url_utils.py`** — `normalize_article_url()` + `article_exists_for_url()` used in `scrape_source`.
- **`articles/cluster_dedup.py`** — before creating a cluster, `find_matching_topic_cluster()` merges into a recent cluster in the same tab (72h, similarity ≥ 0.35).
- **`dedupe_topic_clusters`** management command — one-time cleanup for clusters already duplicated in the DB.

## Clean up production

After deploy, on the API host (or `docker compose exec api`):

```bash
python manage.py dedupe_topic_clusters --dry-run
python manage.py dedupe_topic_clusters
```

Optional single tab:

```bash
python manage.py dedupe_topic_clusters --tab india
```

Then clear feed cache (the command does this when clusters are deleted) or wait up to 5 minutes for `list_cached` TTL.

## Verify

```bash
python manage.py test articles.tests.test_cluster_dedup articles.tests.test_url_utils worker.tests.test_tasks.ClusterAndSummarizeTaskTest -v2
```

New scrapes should not create duplicate cards for the same canonical URL or near-duplicate titles in the same tab.
