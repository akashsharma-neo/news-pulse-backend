"""Helpers for cluster summaries without LLM (local dev / admin skip)."""

from __future__ import annotations

from django.utils import timezone

from articles.models import Article, TopicCluster
from worker.article_content import fallback_summary_from_article


def mark_pending_cluster_summaries() -> int:
    """Fill empty TopicCluster.summary from primary article text (no LLM).

    Returns:
        Number of clusters updated.
    """
    updated = 0
    qs = TopicCluster.objects.filter(summary="").select_related("primary_article")
    for cluster in qs.iterator():
        cluster.summary = fallback_summary_from_article(cluster.primary_article)
        cluster.save(update_fields=["summary"])
        updated += 1
    return updated


def prune_content_before(cutoff) -> dict[str, int]:
    """Delete clusters and articles older than ``cutoff`` (timezone-aware datetime).

    Clusters are removed first so member articles are not left pointing at deleted rows.
    Articles are then deleted by ``fetched_at``.

    Returns:
        Counts keyed by ``clusters_deleted`` and ``articles_deleted``.
    """
    clusters_deleted, _ = TopicCluster.objects.filter(
        created_at__lt=cutoff,
    ).delete()
    articles_deleted, _ = Article.objects.filter(
        fetched_at__lt=cutoff,
    ).delete()
    return {
        "clusters_deleted": clusters_deleted,
        "articles_deleted": articles_deleted,
    }


def start_of_today():
    """Local timezone start of the current calendar day."""
    now = timezone.localtime(timezone.now())
    return now.replace(hour=0, minute=0, second=0, microsecond=0)
