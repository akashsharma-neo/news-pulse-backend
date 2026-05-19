"""Detect and merge duplicate story clusters in the same tab."""

from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from articles.models import Article, TopicCluster

# Slightly stricter than batch clustering (0.2) — reduces false merges on the feed.
CLUSTER_MATCH_THRESHOLD = 0.35
CLUSTER_MATCH_WINDOW_HOURS = 72


def story_similarity(article_a: Article, article_b: Article, *, title_similarity) -> float:
    """Combined title + content similarity between two articles."""
    title_sim = title_similarity(article_a.title, article_b.title)
    text_a = (article_a.title + " " + (article_a.full_text or "")).lower()
    text_b = (article_b.title + " " + (article_b.full_text or "")).lower()
    tokens_a = set(_tokenize(text_a))
    tokens_b = set(_tokenize(text_b))
    if not tokens_a or not tokens_b:
        content_sim = 0.0
    else:
        intersection = len(tokens_a & tokens_b)
        union = len(tokens_a | tokens_b)
        content_sim = intersection / union if union else 0.0
    return 0.6 * title_sim + 0.4 * content_sim


def _tokenize(text: str) -> list[str]:
    import re

    return re.findall(r"[a-z0-9]{2,}", text.lower())


def find_matching_topic_cluster(
    article: Article,
    *,
    category_slug: str,
    title_similarity,
    threshold: float = CLUSTER_MATCH_THRESHOLD,
    window_hours: int = CLUSTER_MATCH_WINDOW_HOURS,
    exclude_cluster_ids: set[int] | None = None,
) -> TopicCluster | None:
    """Return a recent TopicCluster in the same tab that covers the same story."""
    cutoff = timezone.now() - timedelta(hours=window_hours)
    exclude_cluster_ids = exclude_cluster_ids or set()

    candidates = (
        TopicCluster.objects.filter(
            primary_article__source__category__slug=category_slug,
            created_at__gte=cutoff,
        )
        .exclude(pk__in=exclude_cluster_ids)
        .select_related("primary_article")
        .order_by("-created_at")[:80]
    )

    best: TopicCluster | None = None
    best_sim = 0.0
    for cluster in candidates:
        primary = cluster.primary_article
        if not primary:
            continue
        sim = story_similarity(article, primary, title_similarity=title_similarity)
        if sim >= threshold and sim > best_sim:
            best_sim = sim
            best = cluster
    return best


def merge_articles_into_cluster(
    cluster: TopicCluster,
    articles: list[Article],
) -> TopicCluster:
    """Attach articles to an existing cluster and refresh metadata."""
    if not articles:
        return cluster

    member_ids = [a.pk for a in articles]
    Article.objects.filter(pk__in=member_ids).update(topic_cluster=cluster)

    names = set(cluster.source_names())
    for article in articles:
        if article.source:
            names.add(article.source.name)

    newest = max(
        articles + ([cluster.primary_article] if cluster.primary_article else []),
        key=lambda a: a.published_at or a.fetched_at,
    )
    update_fields = ["sources"]
    cluster.sources = sorted(names)
    if cluster.primary_article_id != newest.pk:
        cluster.primary_article = newest
        update_fields.append("primary_article")
    cluster.save(update_fields=update_fields)
    return cluster


def dedupe_clusters_for_tab(
    category_slug: str,
    *,
    title_similarity,
    threshold: float = CLUSTER_MATCH_THRESHOLD,
    window_hours: int = CLUSTER_MATCH_WINDOW_HOURS,
    dry_run: bool = False,
) -> dict[str, int]:
    """Merge duplicate TopicClusters in one tab (keeps newest cluster per story)."""
    cutoff = timezone.now() - timedelta(hours=window_hours)
    clusters = list(
        TopicCluster.objects.filter(
            primary_article__source__category__slug=category_slug,
            created_at__gte=cutoff,
        )
        .select_related("primary_article", "primary_article__source")
        .order_by("-created_at")
    )

    merged = 0
    deleted = 0
    kept_ids: set[int] = set()

    for cluster in clusters:
        if cluster.pk in kept_ids:
            continue
        primary = cluster.primary_article
        if not primary:
            continue

        duplicates: list[TopicCluster] = []
        for other in clusters:
            if other.pk == cluster.pk or other.pk in kept_ids:
                continue
            other_primary = other.primary_article
            if not other_primary:
                continue
            sim = story_similarity(
                primary, other_primary, title_similarity=title_similarity
            )
            if sim >= threshold:
                duplicates.append(other)

        if not duplicates:
            kept_ids.add(cluster.pk)
            continue

        keeper = cluster
        for dup in duplicates:
            members = list(dup.member_articles.all())
            if not dry_run:
                merge_articles_into_cluster(keeper, members)
            kept_ids.add(dup.pk)

        if not dry_run:
            dup_ids = [d.pk for d in duplicates]
            TopicCluster.objects.filter(pk__in=dup_ids).delete()
        deleted += len(duplicates)
        merged += 1
        kept_ids.add(keeper.pk)

    return {"stories_merged": merged, "clusters_deleted": deleted}
