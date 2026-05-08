"""
NewsPulse worker app — Celery task definitions.

Public tasks:
    scrape_sources      — Dispatch per-source scrape tasks for all active sources.
    scrape_source       — Fetch articles from a single Source (web/RSS).
    cluster_and_summarize — Cluster unclustered articles and create TopicClusters.

Private helpers:
    _fetch_page                — HTTP fetcher with retry logic.
    _parse_rss_articles        — RSS feed parser using feedparser.
    _extract_web_articles      — Web scraper using BeautifulSoup.
    _tokenize                  — Text tokenizer (lowercase, alphanumeric tokens).
    _title_similarity          — Jaccard similarity between two titles.
    _content_similarity        — Jaccard similarity between article text.
    _cluster_articles_by_similarity — Greedy agglomerative clustering.
"""
