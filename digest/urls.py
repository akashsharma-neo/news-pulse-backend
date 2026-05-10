"""
NewsPulse digest API URL configuration.

Routes:
    POST /api/digest/subscribe/     — Subscribe to daily digest
    GET  /api/digest/unsubscribe/   — Unsubscribe via token
    POST /api/digest/resend/        — Manually trigger digest (dev/admin)
"""

from django.urls import path

from .views import SubscribeView, UnsubscribeView, ResendDigestView

urlpatterns = [
    path("subscribe/", SubscribeView.as_view(), name="subscribe"),
    path("unsubscribe/", UnsubscribeView.as_view(), name="unsubscribe"),
    path("resend/", ResendDigestView.as_view(), name="resend"),
]
