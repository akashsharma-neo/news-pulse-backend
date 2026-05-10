"""
NewsPulse chat API URL configuration.
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ChatMessageViewSet

router = DefaultRouter()
router.register(r'messages', ChatMessageViewSet, basename='chatmessage')

urlpatterns = [path("", include(router.urls))]
