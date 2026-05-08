"""
NewsPulse chat API URL configuration.

Placeholder — future endpoints for article chat threads.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ChatMessageViewSet
from .serializers import ChatMessageSerializer

router = DefaultRouter()
router.register(r'messages', ChatMessageViewSet, basename='chatmessage')

urlpatterns = [path("", include(router.urls))]
