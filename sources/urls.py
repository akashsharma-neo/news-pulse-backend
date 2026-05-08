"""
NewsPulse source API URL configuration.

Registers a REST router for sources under /api/.

URL patterns:
    /api/sources/          — SourceViewSet (read-only, active sources only)
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import SourceViewSet

router = DefaultRouter()
router.register(r"sources", SourceViewSet, basename="source")

urlpatterns = [path("", include(router.urls))]
