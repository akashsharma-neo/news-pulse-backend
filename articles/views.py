"""
NewsPulse article API views.

Provides read-only endpoints for TopicClusters and Articles with
tab-based filtering and ordering.
"""

from django.db.models import F
from django.db.models.functions import Coalesce

from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Tab, TopicCluster, Article
from .serializers import TopicClusterSerializer, ArticleSerializer, TabSerializer


def cluster_feed_queryset(tab: str | None = None):
    """Topic clusters for the tab feed, newest stories first."""
    qs = (
        TopicCluster.objects.select_related(
            "primary_article",
            "primary_article__source",
            "primary_article__source__category",
        )
        .annotate(
            story_published_at=Coalesce(
                F("primary_article__published_at"),
                F("created_at"),
            )
        )
        .order_by("-story_published_at", "-created_at")
    )
    if tab:
        qs = qs.filter(primary_article__source__category__slug=tab)
    return qs


class TopicClusterViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only API for topic clusters (grouped news stories).

    Endpoints:
        GET /api/clusters/          — List clusters (optional ?tab=<slug>)
        GET /api/clusters/<id>/     — Retrieve a single cluster
        GET /api/clusters/tabs/     — List all available tabs

    Query parameters:
        tab: Filter clusters by tab slug (e.g. 'india', 'sports').
        ordering: Sort by primary article publish time or cluster created_at.
        page: Page number for pagination.
    """

    serializer_class = TopicClusterSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = [
        "primary_article__published_at",
        "story_published_at",
        "created_at",
    ]
    ordering = ["-primary_article__published_at", "-created_at"]

    def get_queryset(self):
        """Return feed-ready clusters; detail allows clusters still awaiting summary."""
        base = TopicCluster.objects.select_related(
            "primary_article",
            "primary_article__source",
            "primary_article__source__category",
        )
        if self.action == "retrieve":
            return base
        tab = self.request.query_params.get("tab")
        return cluster_feed_queryset(tab=tab or None)

    @action(detail=False, methods=["get"])
    def tabs(self, request):
        """GET /api/clusters/tabs/ — list navigation tabs."""
        return Response(TabSerializer(Tab.objects.all(), many=True).data)

    @action(detail=True, methods=["get"])
    def related(self, request, pk=None):
        """GET /api/clusters/{id}/related/ — recent clusters in the same tab."""
        cluster = self.get_object()
        limit = min(int(request.query_params.get("limit", 8)), 20)
        tab_slug = cluster.primary_article.source.category.slug
        qs = cluster_feed_queryset(tab=tab_slug).exclude(pk=cluster.pk)[:limit]
        serializer = TopicClusterSerializer(qs, many=True)
        return Response(serializer.data)

    @action(detail=False, url_path="list_cached", url_name="list_cached")
    def list_cached(self, request):
        """Cached version of the cluster list endpoint.

        Uses CacheManager to cache response based on the 'tab' query parameter.
        """
        from core.cache_utils import CacheManager

        tab = request.query_params.get("tab", "all")
        cache_key = f"clusters_list_v2_{tab}"

        def fetcher():
            qs = cluster_feed_queryset(
                tab=None if tab == "all" else tab,
            )
            return TopicClusterSerializer(qs, many=True).data

        return Response(CacheManager.get_or_set(cache_key, fetcher, timeout=300))


class ArticleViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only API for individual articles.

    Endpoints:
        GET /api/articles/          — List articles (optional ?tab=<slug>)
        GET /api/articles/<id>/     — Retrieve a single article

    Query parameters:
        tab: Filter articles by tab slug (e.g. 'india', 'sports').
        ordering: Sort by 'published_at' (default, newest first).
        page: Page number for pagination.
    """

    serializer_class = ArticleSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["published_at"]
    ordering = ["-published_at"]

    def get_queryset(self):
        """Return articles with related source/category data prefetched.

        Optionally filters by tab slug from query params.
        """
        qs = Article.objects.select_related(
            "source", "source__category"
        ).all()
        tab = self.request.query_params.get("tab")
        if tab:
            qs = qs.filter(source__category__slug=tab)
        return qs
