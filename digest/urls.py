"""
NewsPulse digest API URL configuration.

Placeholder — future endpoints for digest subscription management.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter

router = DefaultRouter()

urlpatterns = [path("", include(router.urls))]
