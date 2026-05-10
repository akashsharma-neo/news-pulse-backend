"""
NewsPulse article API views.

Provides read-only endpoints for TopicClusters and Articles with
tab-based filtering and ordering.
"""

from rest_framework import viewsets, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import Tab, TopicCluster, Article
from .serializers import TopicClusterSerializer, ArticleSerializer, TabSerializer


class TopicClusterViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only API for topic clusters (grouped news stories).

    Endpoints:
        GET /api/clusters/          — List clusters (optional ?tab=<slug>)
        GET /api/clusters/<id>/     — Retrieve a single cluster
        GET /api/clusters/tabs/     — List all available tabs

    Query parameters:
        tab: Filter clusters by tab slug (e.g. 'india', 'sports').
        ordering: Sort by 'created_at' (default) or 'published_at'.
        page: Page number for pagination.
    """

    serializer_class = TopicClusterSerializer
    filter_backends = [filters.OrderingFilter]
    ordering_fields = ["created_at", "published_at"]
    ordering = ["-created_at"]

    def get_queryset(self):
        """Return clusters with related source/category data prefetched.

        Optionally filters by tab slug from query params.
        """
        qs = TopicCluster.objects.select_related(
            "primary_article",
            "primary_article__source",
            "primary_article__source__category",
        ).all()
        tab = self.request.query_params.get("tab")
        if tab:
            qs = qs.filter(primary_article__source__category__slug=tab)
        return qs

    @action(detail=False, methods=["get"])
    def tabs(self, request):
        """GET /api/clusters/tabs/ — list navigation tabs."""
        return Response(TabSerializer(Tab.objects.all(), many=True).data)

    @action(detail=False, url_path="list_cached", url_name="list_cached")
    def list_cached(self, request):
        """Cached version of the cluster list endpoint.
        
        Uses CacheManager to cache response based on the 'tab' query enough parameter.
        """
        from core.cache_utils import CacheManager
        
        tab = request.query_params.get("tab", "all")
        cache_key = f"clusters_list_{tab}"

        def fetcher():
            qs = TopicCluster.objects.select_related(
                "primary_article",
                "primary_article__source",
                "primary_article__source__category",
            ).all()
            if tab != "all":
                qs = qs.filter(primary_article__source__category__slug=tab)
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
    filter_backends = []
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
