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
from .views import TopicClusterViewSet, ArticleViewSet

router = DefaultRouter()
router.register(r"clusters", TopicClusterViewSet, basename="cluster")
router.register(r"articles", ArticleViewSet, basename="article")

urlpatterns = [path("", include(router.urls))]
