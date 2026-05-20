"""
NewsPulse users app URL configuration.

Registers REST routers for personalization endpoints under /api/.

URL patterns:
    /api/interactions/              — Record/list user interactions
    /api/interactions/by-session/   — List interactions for a session
    /api/affinity/                  — Compute topic affinity profile
    /api/affinity/history/          — Affinity evolution over time
    /api/personalized-clusters/     — Personalized ("Just For You") feed
    /api/auth/register/             — Register a new user
    /api/auth/login/                — Login and obtain tokens
    /api/auth/me/                   — Current user profile
    /api/auth/logout/               — Logout (blacklist refresh token)
    /api/auth/refresh/              — Refresh access token
"""

from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    InteractionViewSet,
    AffinityViewSet,
    PersonalizedClusterViewSet,
    RegisterView,
    LoginView,
    MeView,
    LogoutView,
    VerifyEmailView,
    ResendVerificationView,
    FirebaseAuthView,
)

# Personalization router
router = DefaultRouter()
router.register(r"interactions", InteractionViewSet, basename="interaction")
router.register(r"affinity", AffinityViewSet, basename="affinity")
# Use a different prefix to avoid conflict with articles TopicClusterViewSet
router.register(r"personalized-clusters", PersonalizedClusterViewSet, basename="personalized-cluster")

# Auth URLs
urlpatterns = [
    path("", include(router.urls)),
    path("auth/register/", RegisterView.as_view(), name="register"),
    path("auth/login/", LoginView.as_view(), name="login"),
    path("auth/verify-email/", VerifyEmailView.as_view(), name="verify-email"),
    path("auth/resend-verification/", ResendVerificationView.as_view(), name="resend-verification"),
    path("auth/firebase/", FirebaseAuthView.as_view(), name="firebase-auth"),
    path("auth/me/", MeView.as_view(), name="me"),
    path("auth/logout/", LogoutView.as_view(), name="logout"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="token-refresh"),
]
