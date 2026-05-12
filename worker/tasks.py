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
from celery import shared_task
from celery.utils.log import get_task_logger
from django.utils import timezone as dj_timezone
from feedparser import parse as parse_rss

from articles.models import Article, Source, Tab, TopicCluster

logger = get_task_logger(__name__)

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


def _extract_web_articles(html: str, config: dict) -> list[dict]:
    """Extract articles from a web page using CSS selectors."""
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

        # Resolve relative URLs
        if url.startswith("//"):
            url = "https:" + url
        elif url.startswith("/"):
            url = "https://newspulse.app" + url  # placeholder base

        # Find content
        content_el = None
        for sel in content_selectors:
            content_el = container.select_one(sel)
            if content_el:
                break
        if not content_el:
            content_el = container

        content = content_el.get_text(strip=True)[:2000]

        articles.append({
            "title": title,
            "url": url,
            "content": content,
        })

    return articles


def _parse_rss_articles(html: str, source_name: str) -> list[dict]:
    """Parse RSS feed and return list of article dicts."""
    feed = parse_rss(html)
    articles = []
    for entry in feed.entries[:50]:  # cap at 50 per source
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        content = entry.get("summary", entry.get("description", "")).strip()[:2000]

        if not title or not link:
            continue

        # Parse published date
        published_at = None
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            published_at = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
            published_at = datetime(*entry.updated_parsed[:6], tzinfo=timezone.utc)

        articles.append({
            "title": title,
            "url": link,
            "content": content,
            "published_at": published_at,
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
        articles_data = _extract_web_articles(html, config)

    fetched = len(articles_data)
    created = 0
    skipped = 0

    for article_data in articles_data:
        # Check if we already have this URL
        if Article.objects.filter(url=article_data["url"]).exists():
            skipped += 1
            continue

        # Normalize published_at
        pub_at = article_data.get("published_at")
        if pub_at is None:
            pub_at = dj_timezone.now()

        Article.objects.create(
            title=article_data["title"],
            url=article_data["url"],
            source=source,
            full_text=article_data.get("content", ""),
            published_at=pub_at,
        )
        created += 1

    logger.info(
        "Source %s done: fetched=%d created=%d skipped=%d",
        source.name, fetched, created, skipped,
    )
    return {"fetched": fetched, "created": created, "skipped": skipped}


@shared_task
def scrape_sources() -> dict:
    """
    Main entry point: scrape all active sources.

    Dispatches per-source tasks and returns aggregate results.
    """
    active_sources = list(Source.objects.filter(active=True).values_list("id", "name"))

    if not active_sources:
        logger.warning("No active sources configured")
        return {"total_fetched": 0, "total_created": 0, "total_skipped": 0, "details": []}

    results = []
    for source_id, source_name in active_sources:
        result = scrape_source.delay(source_id)
        results.append({
            "source": source_name,
            "task_id": result.id,
        })

    logger.info("Dispatched %d scrape tasks", len(results))
    return {"dispatched": len(results), "tasks": results}


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

    An article is "unclustered" if it has no TopicCluster reference.
    We cluster articles from the last 48 hours.

    Returns {"clusters_created": N, "articles_clustered": N, "leftover": N}
    """
    from datetime import timedelta

    cutoff = dj_timezone.now() - timedelta(hours=48)

    # Get unclustered articles from the last 48 hours
    unclustered = Article.objects.filter(
        fetched_at__gte=cutoff,
    ).exclude(
        pk__in=TopicCluster.objects.values_list("primary_article_id", flat=True)
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

            # Create TopicCluster
            TopicCluster.objects.create(
                topic_id=uuid.uuid4(),
                primary_article=primary,
                summary="",  # Will be filled by summarization task (1.6)
                sources=source_names,
            )
            total_clusters += 1
            total_clustered += len(cluster_articles)

            logger.info(
                "Cluster %s: %d articles, primary='%s'",
                cat_slug, len(cluster_articles), primary.title[:60],
            )

    # Dispatch summarization task for the newly created clusters
    if total_clusters > 0:
        summarize_clusters.delay()

    # Count leftover (singletons — articles with no similar match)
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


@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def summarize_clusters(self) -> dict:
    """
    Generate AI summaries for TopicClusters with empty summaries.

    Calls OpenAI to produce a concise 60-80 word summary based on the
    primary article's title, content, and source information.

    Returns {"summarized": N, "skipped": N}.
    """
    from django.conf import settings

    empty_clusters = TopicCluster.objects.filter(summary="")
    if not empty_clusters.exists():
        logger.info("No clusters need summarization")
        return {"summarized": 0, "skipped": 0}

    try:
        from openai import OpenAI
        client = OpenAI(api_key=settings.OPENAI_API_KEY, base_url=settings.OPENAI_BASE_URL)
        model = getattr(settings, "OPENAI_MODEL", "gpt-4o-mini")
    except Exception as exc:
        logger.error("Failed to initialize OpenAI client: %s", exc)
        raise self.retry(exc=exc)

    summarized = 0
    skipped = 0

    for cluster in empty_clusters:
        article = cluster.primary_article
        if not article:
            skipped += 1
            continue

        title = article.title or ""
        content = article.full_text or ""
        source_name = article.source.name if article.source else "Unknown"
        url = article.url or ""

        prompt = (
            f"Write a concise news summary (60-80 words) of the following article. "
            f"Do not include any introductory phrases — start directly with the summary content.\n\n"
            f"Title: {title}\n"
            f"Source: {source_name}\n"
            f"URL: {url}\n"
            f"Content: {content[:3000]}"
        )

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200,
                temperature=0.3,
            )
            summary = response.choices[0].message.content.strip()
            cluster.summary = summary
            cluster.save(update_fields=["summary"])
            summarized += 1
            logger.info("Summarized cluster %s: '%s'", cluster.pk, summary[:80])
        except Exception as exc:
            logger.error("Failed to summarize cluster %s: %s", cluster.pk, exc)
            skipped += 1

    return {"summarized": summarized, "skipped": skipped}


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

    Dispatches the full NewsPulse pipeline as a chain of Celery tasks:
    1. Scrape all active sources
    2. Cluster unclustered articles
    3. Summarize clusters (auto-dispatched by cluster_and_summarize)
    4. Generate embeddings for articles
    5. Generate embeddings for clusters

    Returns a summary of dispatched tasks.
    """
    scrape_result = scrape_sources.delay()
    cluster_result = cluster_and_summarize.delay()
    embed_result = generate_embeddings_task.delay()
    cluster_embed_result = generate_cluster_embeddings_task.delay()

    logger.info(
        "Full pipeline dispatched: scrape=%s cluster=%s embed=%s cluster_embed=%s",
        scrape_result.id, cluster_result.id, embed_result.id, cluster_embed_result.id,
    )
    return {
        "scrape_task_id": scrape_result.id,
        "cluster_task_id": cluster_result.id,
        "summarize_task": "auto-dispatched by cluster_and_summarize",
        "embed_task_id": embed_result.id,
        "cluster_embed_task_id": cluster_embed_result.id,
    }
