"""
NewsPulse article API views.

Provides read-only endpoints for TopicClusters and Articles with
tab-based filtering and ordering, plus search/suggestion/trending.
"""

from django.db.models import F
from django.db.models.functions import Coalesce

from rest_framework import viewsets, filters
from rest_framework.decorators import action, api_view
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from .models import Tab, TopicCluster, Article
from .serializers import (
    ArticleSerializer,
    SearchResultSerializer,
    SuggestionSerializer,
    TabSerializer,
    TopicClusterSerializer,
    TrendingSerializer,
)


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


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


class SearchPagination(PageNumberPagination):
    """Pagination for search results — 20 per page, same as feed."""

    page_size = 20
    page_size_query_param = "page_size"


@api_view(["GET"])
def search_view(request):
    """Full-text search across articles.

    GET /api/search/?q=<query>&tab=<slug>&page=1
    Returns paginated article results ranked by relevance.
    """
    from django.contrib.postgres.search import (
        SearchHeadline,
        SearchQuery,
        SearchRank,
        SearchVector,
    )

    q = request.query_params.get("q", "").strip()
    if len(q) < 2:
        return Response({"count": 0, "next": None, "previous": None, "results": []})

    tab = request.query_params.get("tab")
    vector = SearchVector("full_text", weight="B") + SearchVector("title", weight="A")
    query = SearchQuery(q, config="english")
    headline = SearchHeadline(
        "full_text", query, config="english", max_words=30, min_words=10
    )

    articles = (
        Article.objects.select_related("source", "source__category")
        .annotate(rank=SearchRank(vector, query), headline=headline)
        .filter(rank__gte=0.01)
        .order_by("-rank")
    )
    if tab:
        articles = articles.filter(source__category__slug=tab)

    paginator = SearchPagination()
    page = paginator.paginate_queryset(articles, request)
    serializer = SearchResultSerializer(page, many=True)
    return paginator.get_paginated_response(serializer.data)


@api_view(["GET"])
def suggestion_view(request):
    """Autocomplete suggestions using pg_trgm on topic cluster keywords and titles.

    GET /api/search/suggestions/?q=<query>
    Returns up to 10 suggestions (keywords + titles).
    """
    from django.contrib.postgres.search import TrigramSimilarity
    from django.db.models import Func, Value

    q = request.query_params.get("q", "").strip()
    if len(q) < 1:
        return Response([])

    # Keyword suggestions from TopicCluster keywords field
    keyword_suggestions = (
        TopicCluster.objects.exclude(keywords=[])
        .exclude(keywords__isnull=True)
        .annotate(
            kw_text=Func(
                Func("keywords", function="array_to_string"),
                function="lower",
            ),
            similarity=TrigramSimilarity(
                Func(
                    Func("keywords", function="array_to_string"),
                    function="lower",
                ),
                Value(q.lower()),
            ),
        )
        .filter(similarity__gt=0.1)
        .values_list("keywords", flat=True)[:20]
    )

    # Extract matching keywords from clusters
    seen = set()
    suggestions = []
    for kw_list in keyword_suggestions:
        if not isinstance(kw_list, list):
            continue
        for kw in kw_list:
            if kw.lower().startswith(q.lower()) and kw not in seen:
                seen.add(kw)
                suggestions.append({"text": kw, "type": "keyword"})
            if len(suggestions) >= 5:
                break
        if len(suggestions) >= 5:
            break

    # Title suggestions from primary article titles
    title_suggestions = (
        TopicCluster.objects.select_related("primary_article")
        .annotate(
            similarity=TrigramSimilarity(
                "primary_article__title", Value(q)
            )
        )
        .filter(similarity__gt=0.1)
        .order_by("-similarity")[:5]
    )

    for cluster in title_suggestions:
        title = cluster.primary_article.title
        if title and title not in seen:
            seen.add(title)
            suggestions.append({"text": title, "type": "title"})

    return Response(SuggestionSerializer(suggestions[:10], many=True).data)


@api_view(["GET"])
def trending_view(request):
    """Trending topics — tab suggestions + popular clusters from last 24h.

    GET /api/search/trending/
    Returns a mix of tab suggestions and popular clusters.
    """
    from datetime import timedelta

    from django.db.models import Count
    from django.utils import timezone as dj_timezone

    # Tab suggestions
    tabs = Tab.objects.filter(sources__isnull=False).distinct()
    trending = [
        TrendingSerializer({"text": tab.name, "type": "tab", "slug": tab.slug}).data
        for tab in tabs
    ]

    # Popular clusters from last 24h (most clicked)
    cutoff = dj_timezone.now() - timedelta(hours=24)
    popular_ids = (
        TopicCluster.objects.filter(
            interactions__interaction_type="click",
            interactions__created_at__gte=cutoff,
        )
        .values("pk")
        .annotate(click_count=Count("interactions"))
        .order_by("-click_count")
        .values_list("pk", flat=True)[:5]
    )
    popular = TopicCluster.objects.filter(pk__in=list(popular_ids)).select_related(
        "primary_article", "primary_article__source", "primary_article__source__category"
    )

    seen_slugs = {t["slug"] for t in trending if t.get("slug")}
    for cluster in popular:
        slug = cluster.primary_article.source.category.slug
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        trending.append(
            TrendingSerializer(
                {
                    "text": cluster.primary_article.title[:60],
                    "type": "cluster",
                    "slug": slug,
                    "cluster_id": cluster.pk,
                }
            ).data
        )

    return Response(trending[:10])
