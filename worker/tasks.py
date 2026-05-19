"""
Celery tasks for the NewsPulse scraper pipeline.

Tasks:
- scrape_sources: Main entry point. Iterates all active sources, dispatches
  per-source scrape tasks.
- scrape_source: Fetches articles from a single Source (web/RSS/API).
- run_clustering: Triggers the topic clustering + summarization + embedding
  pipeline on unclustered articles.
- generate_embeddings: Generates local-model embeddings for articles
  and clusters, storing them in pgvector.
"""

import logging
import time
import uuid
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup
from celery import chord, group, shared_task
from celery.utils.log import get_task_logger
from django.utils import timezone as dj_timezone
from feedparser import parse as parse_rss

from articles.image_resolver import extract_rss_image, extract_web_image, pick_cluster_image
from articles.models import Article, Source, Tab, TopicCluster
from worker.article_content import (
    MAX_RELATED_ARTICLES_FOR_SUMMARY,
    MIN_BODY_WORDS,
    build_summarize_prompt,
    clean_article_text,
    enrich_article_content,
    extract_listing_content,
    extract_rss_entry_content,
    fallback_summary_from_article,
    gather_articles_for_summary,
    is_summary_too_short,
    is_usable_article_body,
    word_count,
)

logger = get_task_logger(__name__)

CLUSTER_DEBOUNCE_CACHE_KEY = "np:cluster_after_scrape_scheduled"


# ---------------------------------------------------------------------------
# Scraper configuration per source
# ---------------------------------------------------------------------------

SCRAPER_CONFIGS = {
    # --- India ---
    "NDTV": {
        "category": "india",
        "source_type": "rss",
        "url": "https://feeds.ndtv.com/ndtv/index.xml",
    },
    "Times of India": {
        "category": "india",
        "source_type": "web",
        "url": "https://timesofindia.indiatimes.com/india",
        "selector_title": "h1, .tit, [class*='title'], article h2, h3",
        "selector_content": "article, [class*='content'], .article-body, p",
    },
    "Indian Express": {
        "category": "india",
        "source_type": "rss",
        "url": "https://indianexpress.com/feed/",
    },
    "The Hindu": {
        "category": "india",
        "source_type": "rss",
        "url": "https://www.thehindu.com/news/national/feeder/default.rss",
        "selector_content": ".articlebodycontent, .article-section, #content-body",
        "exclude_selectors": ".paywall, .subscribe, [class*='login'], [class*='subscription']",
        "prefer_rss_body": True,
    },
    "Moneycontrol": {
        "category": "business",
        "source_type": "web",
        "url": "https://www.moneycontrol.com/news/india/",
        "selector_title": "h2, h3, [class*='title'], .story-title",
        "selector_content": "p, [class*='content'], .story-text",
    },
    # --- Sports ---
    "ESPNcricinfo": {
        "category": "sports",
        "source_type": "web",
        "url": "https://www.espncricinfo.com/series",
        "selector_title": "h1, h2, h3, [class*='title'], .story-title",
        "selector_content": "p, [class*='content'], .story-text",
    },
    "Sportskeeda": {
        "category": "sports",
        "source_type": "rss",
        "url": "https://www.sportskeeda.com/feed/",
    },
    # --- Business ---
    "Economic Times": {
        "category": "business",
        "source_type": "rss",
        "url": "https://economictimes.indiatimes.com/newsfeed.rss",
    },
    # --- Global ---
    "BBC": {
        "category": "global",
        "source_type": "rss",
        "url": "http://feeds.bbci.co.uk/news/world/rss.xml",
    },
    "CNN": {
        "category": "global",
        "source_type": "rss",
        "url": "http://rss.cnn.com/rss/cnn_world.rss",
    },
    "Reuters": {
        "category": "global",
        "source_type": "rss",
        "url": "https://feeds.reuters.com/reuters/topNews",
    },
    "Al Jazeera": {
        "category": "global",
        "source_type": "rss",
        "url": "https://www.aljazeera.com/xml/rss/all.xml",
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_source_tab_slug(source_name: str) -> str:
    """Return the tab slug for a given source name from the config."""
    cfg = SCRAPER_CONFIGS.get(source_name)
    if cfg:
        return cfg["category"]
    return "global"  # default fallback


def _fetch_page(url: str, headers: dict = None, retries: int = 3) -> str | None:
    """Fetch a URL and return HTML text. Returns None on failure."""
    if headers is None:
        headers = {
            "User-Agent": (
                "NewsPulse/1.0 (News Aggregator; +https://newspulse.app)"
            ),
        }
    last_err = None
    for attempt in range(retries):
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            return resp.text
        except requests.HTTPError as exc:
            last_err = exc
            if 400 <= resp.status_code < 500 and resp.status_code not in (408, 429):
                logger.error("Client error %d for %s: %s", resp.status_code, url, exc)
                return None
            logger.warning("HTTP %d error on attempt %d for %s: %s", resp.status_code, attempt + 1, url, exc)
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
        except requests.RequestException as exc:
            last_err = exc
            logger.warning("Attempt %d failed for %s: %s", attempt + 1, url, exc)
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
    logger.error("All %d attempts failed for %s: %s", retries, url, last_err)
    return None


def invalidate_cluster_feed_cache() -> None:
    """Clear cached cluster list responses so the UI shows new stories."""
    from django.core.cache import cache

    try:
        cache.delete_pattern("clusters_list_v2_*")
    except AttributeError:
        cache.delete("clusters_list_v2_all")


def schedule_cluster_after_scrape(countdown: int = 90) -> bool:
    """
    Debounced cluster run after scrape tasks finish.

    Parallel scrape_source tasks each call this; only one cluster_and_summarize
    is queued per debounce window. Backup when the scrape chord callback does not run.
    """
    from django.core.cache import cache

    ttl = countdown + 60
    if not cache.add(CLUSTER_DEBOUNCE_CACHE_KEY, 1, timeout=ttl):
        return False

    cluster_and_summarize.apply_async(countdown=countdown)
    logger.info("Scheduled cluster_and_summarize in %ss (debounced)", countdown)
    return True


def _extract_web_articles(html: str, config: dict, listing_url: str | None = None) -> list[dict]:
    """Extract articles from a web page using CSS selectors."""
    from urllib.parse import urljoin

    base_url = listing_url or config.get("url", "")
    soup = BeautifulSoup(html, "html.parser")
    articles = []

    # Try to find article containers
    title_selectors = [s.strip() for s in config.get(
        "selector_title", "h1, h2, h3, [class*='title']"
    ).split(",")]
    content_selectors = [s.strip() for s in config.get(
        "selector_content", "p, [class*='content']"
    ).split(",")]

    # Strategy 1: Look for list of articles (common pattern)
    article_containers = soup.select("article, .story, [class*='card'], [class*='item']")
    if not article_containers:
        # Strategy 2: Use title selectors to find individual titles
        article_containers = soup.select(", ".join(title_selectors))

    seen_urls = set()
    for container in article_containers[:50]:  # cap at 50
        # Find title
        title_el = None
        for sel in title_selectors:
            title_el = container.select_one(sel)
            if title_el:
                break
        if not title_el:
            continue

        title = title_el.get_text(strip=True)
        if not title or len(title) < 10:
            continue

        # Find link
        link_el = title_el.find("a", href=True)
        if not link_el:
            link_el = container.find("a", href=True)
        if not link_el:
            continue

        url = link_el["href"]
        if url in seen_urls:
            continue
        seen_urls.add(url)

        # Resolve relative URLs against the listing page
        if url.startswith("//"):
            url = "https:" + url
        elif base_url and (url.startswith("/") or not url.startswith("http")):
            url = urljoin(base_url, url)

        source_image_url = extract_web_image(container, base_url) or ""

        content = extract_listing_content(container, content_selectors)

        articles.append({
            "title": title,
            "url": url,
            "content": content,
            "source_image_url": source_image_url,
        })

    return articles


def _parse_rss_articles(html: str, source_name: str) -> list[dict]:
    """Parse RSS feed and return list of article dicts."""
    feed = parse_rss(html)
    articles = []
    for entry in feed.entries[:50]:  # cap at 50 per source
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        content = extract_rss_entry_content(entry)

        if not title or not link:
            continue

        # Parse published date
        published_at = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
            published_at = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)

        source_image_url = extract_rss_image(entry) or ""

        articles.append({
            "title": title,
            "url": link,
            "content": content,
            "published_at": published_at,
            "source_image_url": source_image_url,
        })

    return articles


# ---------------------------------------------------------------------------
# Celery Tasks
# ---------------------------------------------------------------------------

@shared_task(bind=True, max_retries=2, default_retry_delay=60)
def scrape_source(self, source_id: int) -> dict:
    """
    Scrape articles from a single Source.

    Returns dict with counts: {"fetched": N, "created": N, "skipped": N}
    """
    try:
        try:
            source = Source.objects.get(id=source_id)
        except Source.DoesNotExist:
            logger.error("Source %d not found", source_id)
            return {"fetched": 0, "created": 0, "skipped": 0}

        config = SCRAPER_CONFIGS.get(source.name, {})
        url = config.get("url", source.url)
        source_type = config.get("source_type", source.source_type)

        logger.info("Scraping source: %s (%s) — %s", source.name, source_type, url)

        html = _fetch_page(url)
        if not html:
            raise self.retry(exc=Exception(f"Failed to fetch {url}"))

        if source_type == "rss":
            articles_data = _parse_rss_articles(html, source.name)
        else:
            articles_data = _extract_web_articles(html, config, listing_url=url)

        fetched = len(articles_data)
        created = 0
        skipped = 0

        max_detail_fetches = config.get("max_detail_fetches", 15)
        detail_fetches = 0

        new_articles = [
            ad for ad in articles_data
            if not Article.objects.filter(url=ad["url"]).exists()
        ]
        skipped = fetched - len(new_articles)

        # Prioritize detail-page fetches for thin RSS/listing bodies.
        new_articles.sort(key=lambda ad: word_count(clean_article_text(ad.get("content", ""))))

        for article_data in new_articles:
            content = clean_article_text(article_data.get("content", ""), source.name)
            if detail_fetches < max_detail_fetches and word_count(content) < MIN_BODY_WORDS:
                enriched = enrich_article_content(
                    article_data["url"],
                    content,
                    config,
                    _fetch_page,
                )
                if word_count(enriched) > word_count(content):
                    detail_fetches += 1
                    content = enriched

            content = clean_article_text(content, source.name)

            pub_at = article_data.get("published_at")
            if pub_at is None:
                pub_at = dj_timezone.now()

            Article.objects.create(
                title=article_data["title"][:1000],
                url=article_data["url"][:2048],
                source=source,
                full_text=content,
                published_at=pub_at,
                source_image_url=(article_data.get("source_image_url") or "")[:2048],
            )
            created += 1

        logger.info(
            "Source %s done: fetched=%d created=%d skipped=%d",
            source.name, fetched, created, skipped,
        )
        return {"fetched": fetched, "created": created, "skipped": skipped}
    finally:
        schedule_cluster_after_scrape(countdown=90)


@shared_task
def scrape_sources() -> dict:
    """
    Main entry point: scrape all active sources.

    Runs per-source scrapes in parallel, then clusters and summarizes when all
    scrapes finish (Celery chord). Hourly Beat cluster_and_summarize remains a
    safety net for missed articles.
    """
    active_source_ids = list(
        Source.objects.filter(active=True).values_list("id", flat=True)
    )

    if not active_source_ids:
        logger.warning("No active sources configured")
        return {"dispatched": 0}

    async_result = chord(
        group(scrape_source.s(source_id) for source_id in active_source_ids),
        cluster_and_summarize.si(),
    ).apply_async()

    # Backup if chord callback is lost (e.g. broker flush); scrape_source also debounces.
    schedule_cluster_after_scrape(countdown=180)

    logger.info("Dispatched scrape chord for %d sources", len(active_source_ids))
    return {"dispatched": len(active_source_ids), "chord_id": async_result.id}


# ---------------------------------------------------------------------------
# Topic Clustering (Task 1.5)
# ---------------------------------------------------------------------------


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + lowercase tokenizer."""
    import re
    return re.findall(r"[a-z0-9]{2,}", text.lower())


def _tfidf_vectorize(documents: list[str]) -> tuple[list[list[float]], set[str]]:
    """
    Compute TF-IDF vectors for a list of documents.
    Returns (vectors, vocabulary) — pure Python, no sklearn dependency.
    """
    # Build vocabulary
    doc_tokens = [_tokenize(d) for d in documents]
    vocab: set[str] = set()
    for tokens in doc_tokens:
        vocab.update(tokens)
    vocab = sorted(vocab)
    vocab_index = {w: i for i, w in enumerate(vocab)}

    # Compute term frequencies
    tf_matrix = []
    for tokens in doc_tokens:
        tf = [0.0] * len(vocab)
        for token in tokens:
            idx = vocab_index[token]
            tf[idx] += 1
        # Normalize by document length
        length = len(tokens) if tokens else 1
        tf = [c / length for c in tf]
        tf_matrix.append(tf)

    # Compute inverse document frequency
    n_docs = len(documents)
    idf = [0.0] * len(vocab)
    for j, term in enumerate(vocab):
        doc_count = sum(1 for tokens in doc_tokens if term in tokens)
        if doc_count > 0:
            idf[j] = 1.0 + (n_docs / (1.0 + doc_count))  # smoothed IDF

    # TF-IDF = TF * IDF
    tfidf_matrix = []
    for row in tf_matrix:
        tfidf_matrix.append([row[j] * idf[j] for j in range(len(vocab))])

    return tfidf_matrix, vocab


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _title_similarity(title_a: str, title_b: str) -> float:
    """Compute similarity between two titles using token Jaccard overlap."""
    a = set(_tokenize(title_a))
    b = set(_tokenize(title_b))
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union > 0 else 0.0


def _content_similarity(article_a: Article, article_b: Article) -> float:
    """Compute similarity between article content using token Jaccard overlap."""
    text_a = (article_a.title + " " + article_a.full_text).lower()
    text_b = (article_b.title + " " + article_b.full_text).lower()
    tokens_a = set(_tokenize(text_a))
    tokens_b = set(_tokenize(text_b))
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = len(tokens_a & tokens_b)
    union = len(tokens_a | tokens_b)
    return intersection / union if union > 0 else 0.0


def _cluster_articles_by_similarity(
    articles: list[Article],
    threshold: float = 0.2,
) -> list[list[Article]]:
    """
    Group articles into clusters using title + content similarity.

    Greedy agglomerative clustering:
    1. Sort articles by published_at desc (newest first).
    2. For each unclustered article, find existing clusters with high
       combined title+content similarity and merge if above threshold.
    3. If no existing cluster matches, create a new cluster.

    Returns list of clusters, each a list of Article instances.
    """
    # Sort newest first
    sorted_articles = sorted(articles, key=lambda a: a.published_at or a.fetched_at, reverse=True)

    clusters: list[list[Article]] = []
    cluster_representatives: list[tuple[str, Article]] = []  # (representative_title, representative_article)

    for article in sorted_articles:
        title = article.title
        best_cluster_idx = -1
        best_sim = 0.0

        for idx, (rep_title, rep_article) in enumerate(cluster_representatives):
            # Combine title similarity and content similarity
            title_sim = _title_similarity(title, rep_title)
            content_sim = _content_similarity(article, rep_article)
            # Weighted combination: title is more important
            combined = 0.6 * title_sim + 0.4 * content_sim
            if combined > best_sim:
                best_sim = combined
                best_cluster_idx = idx

        if best_cluster_idx >= 0 and best_sim >= threshold:
            clusters[best_cluster_idx].append(article)
        else:
            clusters.append([article])
            cluster_representatives.append((title, article))

    return clusters


@shared_task
def cluster_and_summarize() -> dict:
    """
    Cluster unclustered articles and create TopicClusters.

    An article is "unclustered" if it has no topic_cluster FK.
    We cluster articles from the last 48 hours.

    Returns {"clusters_created": N, "articles_clustered": N, "leftover": N}
    """
    from datetime import timedelta

    cutoff = dj_timezone.now() - timedelta(hours=48)

    # Get unclustered articles from the last 48 hours
    unclustered = Article.objects.filter(
        fetched_at__gte=cutoff,
        topic_cluster__isnull=True,
    ).order_by("-published_at")

    if not unclustered.exists():
        logger.info("No unclustered articles in the last 48h")
        return {"clusters_created": 0, "articles_clustered": 0, "leftover": 0}

    articles = list(unclustered)
    logger.info("Found %d unclustered articles", len(articles))

    # Group by category (tab) first — don't cluster across tabs
    by_category: dict[str, list[Article]] = {}
    for article in articles:
        cat_slug = article.source.category.slug if article.source.category else "global"
        by_category.setdefault(cat_slug, []).append(article)

    total_clusters = 0
    total_clustered = 0
    total_leftover = 0

    for cat_slug, cat_articles in by_category.items():
        clusters = _cluster_articles_by_similarity(cat_articles, threshold=0.2)

        for cluster_articles in clusters:
            if len(cluster_articles) < 1:
                continue

            # Primary article = newest in cluster
            primary = max(cluster_articles, key=lambda a: a.published_at or a.fetched_at)

            # Collect source names
            source_names = list(set(
                a.source.name for a in cluster_articles if a.source
            ))

            cluster_image_url = pick_cluster_image(
                cluster_articles, primary, cat_slug
            )

            # Create TopicCluster and link all member articles
            cluster = TopicCluster.objects.create(
                topic_id=uuid.uuid4(),
                primary_article=primary,
                summary="",  # Will be filled by summarization task (1.6)
                sources=source_names,
                image_url=cluster_image_url[:2048],
            )
            member_ids = [a.pk for a in cluster_articles]
            Article.objects.filter(pk__in=member_ids).update(topic_cluster=cluster)
            total_clusters += 1
            total_clustered += len(cluster_articles)

            logger.info(
                "Cluster %s: %d articles, primary='%s'",
                cat_slug, len(cluster_articles), primary.title[:60],
            )

    if total_clusters > 0:
        from django.conf import settings

        if settings.SUMMARIZE_ENABLED:
            summarize_clusters.delay()
        invalidate_cluster_feed_cache()

    total_leftover = len(articles) - total_clustered

    logger.info(
        "Clustering done: %d clusters, %d articles grouped, %d leftover",
        total_clusters, total_clustered, total_leftover,
    )
    return {
        "clusters_created": total_clusters,
        "articles_clustered": total_clustered,
        "leftover": total_leftover,
    }


# ---------------------------------------------------------------------------
# Summarization (Task 1.6)
# ---------------------------------------------------------------------------


def _related_articles_for_cluster(
    primary: Article,
    cluster: TopicCluster,
    max_related: int = 1,
) -> list[Article]:
    """Articles in the same tab with similar titles (same-story coverage)."""
    from datetime import timedelta

    if not primary or not primary.source or not primary.source.category_id:
        return []

    window_start = (primary.published_at or primary.fetched_at) - timedelta(hours=72)
    candidates = (
        Article.objects.filter(
            source__category_id=primary.source.category_id,
            published_at__gte=window_start,
        )
        .exclude(pk=primary.pk)
        .select_related("source")
        .order_by("-published_at")[:30]
    )

    related: list[Article] = []
    for candidate in candidates:
        if _title_similarity(primary.title, candidate.title) >= 0.35:
            related.append(candidate)
        if len(related) >= max_related:
            break
    return related


def _ensure_primary_article_body(article: Article, config: dict | None = None) -> str:
    """Return full body text, fetching the article page when stored text is thin."""
    source_name = article.source.name if article.source else ""
    body = clean_article_text(article.full_text or "", source_name)
    if word_count(body) >= MIN_BODY_WORDS and is_usable_article_body(body, source_name):
        return body

    cfg = config or SCRAPER_CONFIGS.get(source_name, {})
    enriched = enrich_article_content(article.url, body, cfg, _fetch_page)
    enriched = clean_article_text(enriched, source_name)
    if word_count(enriched) > word_count(body):
        article.full_text = enriched
        article.save(update_fields=["full_text"])
        return enriched
    return body


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def summarize_clusters(self) -> dict:
    """
    Generate AI summaries for TopicClusters with empty summaries.

    Calls OpenAI to produce a ~100-120 word summary from cluster member
    article bodies (primary + related members).

    Returns {"summarized": N, "skipped": N}.
    """
    from django.conf import settings

    if not settings.SUMMARIZE_ENABLED:
        logger.info("Summarization disabled (SUMMARIZE_ENABLED=false)")
        return {"summarized": 0, "skipped": 0, "disabled": True}

    summarize_batch_size = settings.SUMMARIZE_BATCH_SIZE
    summarize_delay_sec = settings.SUMMARIZE_DELAY_SEC
    summarize_max_tokens = settings.SUMMARIZE_MAX_TOKENS
    fetch_full_body = settings.SUMMARIZE_FETCH_FULL_BODY

    empty_clusters = TopicCluster.objects.filter(summary="")
    if not empty_clusters.exists():
        logger.info("No clusters need summarization")
        return {"summarized": 0, "skipped": 0}

    try:
        from openai import OpenAI, RateLimitError
        client = OpenAI(
            api_key=settings.OPENAI_COMPATIBLE_API_KEY,
            base_url=settings.OPENAI_COMPATIBLE_BASE_URL,
        )
        model = settings.OPENAI_COMPATIBLE_MODEL
    except Exception as exc:
        logger.error("Failed to initialize OpenAI client: %s", exc)
        raise self.retry(exc=exc)

    pending = empty_clusters.order_by("created_at")
    pending_total = pending.count()
    batch = list(pending[:summarize_batch_size])

    summarized = 0
    skipped = 0
    rate_limited = False

    for cluster in batch:
        article = cluster.primary_article
        if not article:
            skipped += 1
            continue

        source_name = article.source.name if article.source else "Unknown"
        url = article.url or ""
        title = article.title or ""
        source_names = cluster.source_names()

        if len(source_names) <= 1 and is_usable_article_body(article.full_text or "", source_name):
            cluster.summary = fallback_summary_from_article(article)
            cluster.save(update_fields=["summary"])
            summarized += 1
            logger.info(
                "Excerpt summary for cluster %s (single-source, no LLM)",
                cluster.pk,
            )
            continue

        source_cfg = SCRAPER_CONFIGS.get(source_name, {})
        if fetch_full_body or word_count(clean_article_text(article.full_text or "")) < 20:
            _ensure_primary_article_body(article, source_cfg)

        related: list[Article] = list(
            cluster.member_articles.exclude(pk=article.pk)
            .select_related("source")[:MAX_RELATED_ARTICLES_FOR_SUMMARY]
        )
        if fetch_full_body:
            for related_article in related:
                related_cfg = SCRAPER_CONFIGS.get(
                    related_article.source.name if related_article.source else "",
                    {},
                )
                _ensure_primary_article_body(related_article, related_cfg)

        source_material = gather_articles_for_summary(
            article, related, source_names,
        )
        if word_count(source_material) < 20:
            logger.warning(
                "Insufficient source text for cluster %s (words=%d)",
                cluster.pk,
                word_count(source_material),
            )
            skipped += 1
            continue

        prompt = build_summarize_prompt(
            title=title,
            source_name=source_name,
            url=url,
            source_material=source_material,
            source_names=source_names,
        )

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=summarize_max_tokens,
                temperature=0.3,
            )
            raw = response.choices[0].message.content or ""
            summary = raw.strip()
            if not summary or is_summary_too_short(summary):
                logger.warning(
                    "Summary too short for cluster %s (words=%d, finish_reason=%s)",
                    cluster.pk,
                    word_count(summary),
                    response.choices[0].finish_reason,
                )
                skipped += 1
                continue
            cluster.summary = summary
            cluster.save(update_fields=["summary"])
            summarized += 1
            logger.info("Summarized cluster %s: '%s'", cluster.pk, summary[:80])
        except RateLimitError as exc:
            logger.warning("Rate limited while summarizing cluster %s: %s", cluster.pk, exc)
            rate_limited = True
            skipped += 1
            break
        except Exception as exc:
            logger.error("Failed to summarize cluster %s: %s", cluster.pk, exc)
            skipped += 1

        if summarize_delay_sec > 0:
            time.sleep(summarize_delay_sec)

    if rate_limited:
        raise self.retry(countdown=60)

    remaining = TopicCluster.objects.filter(summary="").count()
    if remaining > 0 and summarized > 0:
        summarize_clusters.delay()

    return {
        "summarized": summarized,
        "skipped": skipped,
        "pending": pending_total,
        "remaining": remaining,
    }


# ---------------------------------------------------------------------------
# Embedding Pipeline (Task 1.7)
# ---------------------------------------------------------------------------


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def generate_embeddings_task(
    self,
    model_name: str = "all-mpnet-base-v2",
    batch_size: int = 64,
    field: str = "summary",
) -> dict:
    """
    Generate embeddings for articles missing vectors.

    Uses a local ``sentence-transformers`` model to encode article
    summaries (or titles as fallback) and stores the resulting 768-dim
    vectors in the ``pgvector`` column on ``Article``.

    Args:
        model_name: HuggingFace model identifier (default:
            ``all-mpnet-base-v2``, 768-dim).
        batch_size: Articles per model forward pass.
        field: Model field to embed — ``summary``, ``title``, or
            ``full_text``.

    Returns:
        Dict with counts:
        ``{"generated": N, "skipped_empty": N, "updated": N}``
    """
    from django.conf import settings

    if not settings.EMBEDDINGS_ENABLED:
        logger.info("Embeddings disabled (EMBEDDINGS_ENABLED=false); skipping")
        return {"generated": 0, "skipped_empty": 0, "updated": 0, "disabled": True}

    try:
        from worker.embeddings import generate_embeddings

        result = generate_embeddings(
            model_name=model_name,
            batch_size=batch_size,
            field=field,
        )
        logger.info("Embedding task complete: %s", result)
        return result
    except Exception as exc:
        logger.error("Embedding task failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def generate_cluster_embeddings_task(
    self,
    model_name: str = "all-mpnet-base-v2",
    batch_size: int = 64,
) -> dict:
    """
    Generate embeddings for TopicCluster summaries.

    Builds text from each cluster's summary + source names, embeds via
    the local model, and stores the vector on the primary article.

    Args:
        model_name: HuggingFace model identifier.
        batch_size: Clusters per model forward pass.

    Returns:
        Dict with counts:
        ``{"generated": N, "updated": N}``
    """
    from django.conf import settings

    if not settings.EMBEDDINGS_ENABLED:
        logger.info("Embeddings disabled (EMBEDDINGS_ENABLED=false); skipping")
        return {"generated": 0, "updated": 0, "disabled": True}

    try:
        from worker.embeddings import generate_cluster_embeddings

        result = generate_cluster_embeddings(
            model_name=model_name,
            batch_size=batch_size,
        )
        logger.info("Cluster embedding task complete: %s", result)
        return result
    except Exception as exc:
        logger.error("Cluster embedding task failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc)


@shared_task
def run_full_pipeline() -> dict:
    """
    Run the complete pipeline: scrape → cluster → summarize → embed.

    Dispatches the full NewsPulse pipeline:
    1. Scrape all active sources (chord callback runs cluster + summarize)
    2. Generate embeddings for articles (embeddings queue)
    3. Generate embeddings for clusters (embeddings queue)

    Returns a summary of dispatched tasks.
    """
    from django.conf import settings

    scrape_result = scrape_sources.delay()
    result = {
        "scrape_chord_id": scrape_result.id,
        "summarize_task": "auto-dispatched by cluster_and_summarize via scrape chord",
    }

    if settings.EMBEDDINGS_ENABLED:
        embed_result = generate_embeddings_task.delay()
        cluster_embed_result = generate_cluster_embeddings_task.delay()
        result["embed_task_id"] = embed_result.id
        result["cluster_embed_task_id"] = cluster_embed_result.id
        logger.info(
            "Full pipeline dispatched: scrape_chord=%s embed=%s cluster_embed=%s",
            scrape_result.id,
            embed_result.id,
            cluster_embed_result.id,
        )
    else:
        logger.info(
            "Full pipeline dispatched: scrape_chord=%s (embeddings disabled)",
            scrape_result.id,
        )

    return result
