"""Helpers for cluster summaries without LLM (local dev / admin skip)."""

from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from articles.models import Article, TopicCluster
from worker.article_content import fallback_summary_from_article

def _deleted_count(
    deletion_result: tuple[int, dict[str, int]],
    model,
) -> int:
    """Per-model delete count from ``QuerySet.delete()`` (not the cascade total)."""
    return deletion_result[1].get(model._meta.label, 0)


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


def _article_ids_linked_to_clusters_after(cutoff):
    """Article PKs that must not be deleted (would CASCADE-drop kept clusters)."""
    return Article.objects.filter(
        Q(clustered_as_primary__created_at__gte=cutoff)
        | Q(topic_cluster__created_at__gte=cutoff),
    ).values_list("pk", flat=True)


def prune_content_before(cutoff) -> dict[str, int]:
    """Delete clusters and articles older than ``cutoff`` (timezone-aware datetime).

    Clusters with ``created_at < cutoff`` are removed first. Articles with
    ``fetched_at < cutoff`` are removed next, except any article that is still
    the primary (or a member) of a cluster with ``created_at >= cutoff`` — deleting
    those would CASCADE-remove clusters we intend to keep.

    Returns:
        Per-model counts keyed by ``clusters_deleted`` and ``articles_deleted``.
    """
    cluster_result = TopicCluster.objects.filter(created_at__lt=cutoff).delete()
    clusters_deleted = _deleted_count(cluster_result, TopicCluster)

    protected_ids = _article_ids_linked_to_clusters_after(cutoff)
    article_result = (
        Article.objects.filter(fetched_at__lt=cutoff)
        .exclude(pk__in=protected_ids)
        .delete()
    )
    articles_deleted = _deleted_count(article_result, Article)

    return {
        "clusters_deleted": clusters_deleted,
        "articles_deleted": articles_deleted,
    }


def start_of_today():
    """Local timezone start of the current calendar day."""
    now = timezone.localtime(timezone.now())
    return now.replace(hour=0, minute=0, second=0, microsecond=0)
