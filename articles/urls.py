"""
NewsPulse article API URL configuration.

Registers REST routers for clusters and articles under /api/.

URL patterns:
    /api/clusters/          — TopicClusterViewSet
    /api/clusters/<id>/     — Single cluster detail
    /api/clusters/tabs/     — List all tabs
    /api/articles/          — ArticleViewSet
    /api/articles/<id>/     — Single article detail
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    ArticleViewSet,
    TopicClusterViewSet,
    search_view,
    suggestion_view,
    trending_view,
)

router = DefaultRouter()
router.register(r"clusters", TopicClusterViewSet, basename="cluster")
router.register(r"articles", ArticleViewSet, basename="article")

urlpatterns = [
    path("", include(router.urls)),
    path("search/", search_view, name="search"),
    path("search/suggestions/", suggestion_view, name="search-suggestions"),
    path("search/trending/", trending_view, name="search-trending"),
]
