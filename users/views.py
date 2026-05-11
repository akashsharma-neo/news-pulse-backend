"""
NewsPulse personalization API views.

Provides endpoints for recording user interactions and fetching
a personalized ("Just For You") feed ranked by topic affinity.

Endpoints:
    POST /api/interactions/            — Record a click/save/dwell
    GET  /api/interactions/            — List interactions for a session
    GET  /api/clusters/personalized/   — Personalized feed (affinity-ranked)
    GET  /api/affinity/                — Current affinity profile for a session

Auth endpoints:
    POST /api/auth/register/           — Register a new user
    POST /api/auth/login/              — Login and obtain tokens
    GET  /api/auth/me/                 — Current user profile
    POST /api/auth/logout/             — Logout (blacklist refresh token)
"""

import uuid
import math
from datetime import timedelta, datetime, timezone

from rest_framework import viewsets, status, filters
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.views import TokenRefreshView

from django.utils import timezone as django_tz
from django.db.models import Q, F, Sum, Case, When, IntegerField

from articles.models import TopicCluster, Tab
from articles.serializers import TopicClusterSerializer
from .models import UserInteraction, UserPreference, User
from .serializers import (
    UserInteractionSerializer,
    UserPreferenceSerializer,
    PersonalizedRankScoreSerializer,
    UserRegisterSerializer,
    UserSerializer,
    TokenObtainPairSerializer,
)

# ---------------------------------------------------------------------------
# Affinity constants
# ---------------------------------------------------------------------------
# Exponential decay half-life in hours (7 days)
AFFINITY_HALF_LIFE_HOURS = 7 * 24
# Decay factor derived from half-life: decay = ln(2) / half_life
_AFFINITY_DECAY = math.log(2) / AFFINITY_HALF_LIFE_HOURS
# Interaction type weights for affinity scoring
_INTERACTION_WEIGHTS = {
    "click": 1.0,
    "save": 3.0,
    "dwell": 0.5,
}
# Recency boost: how much a fresh cluster gets (0.0–1.0)
_RECENTNESS_BONUS_MAX = 0.3
_RECENTNESS_WINDOW_HOURS = 24


def _decay_factor(hours_old: float) -> float:
    """Compute exponential decay weight for an interaction.

    Interactions newer than ``hours_old`` get a higher weight.
    Half-life is ~7 days, so an interaction from 7 days ago counts
    at 50% of a fresh one.

    Args:
        hours_old: How many hours ago the interaction occurred.

    Returns:
        Float in (0, 1] — the weight to apply to this interaction.
    """
    if hours_old < 0:
        hours_old = 0
    return math.exp(-_AFFINITY_DECAY * hours_old)


def _get_session_id(request) -> str:
    """Extract or generate a session ID from the request.

    Checks:
        1. ``session_id`` query parameter (for testing/anonymous tracking)
        2. ``X-Session-ID`` header (for SPA cookie-less tracking)

    If neither exists, generates a new UUID and returns it.
    In production, the Next.js app should generate a UUID and send it
    as a cookie or header.

    Args:
        request: The incoming request (WSGIRequest or DRF Request).

    Returns:
        A session ID string (UUID format).
    """
    # Handle both DRF Request and raw WSGIRequest
    if hasattr(request, "query_params"):
        session_id = request.query_params.get("session_id")
    else:
        session_id = request.GET.get("session_id")
    if not session_id:
        if hasattr(request, "headers"):
            session_id = request.headers.get("X-Session-ID")
        else:
            session_id = request.META.get("HTTP_X_SESSION_ID")
    if not session_id:
        session_id = str(uuid.uuid4())
    return session_id


# ---------------------------------------------------------------------------
# Auth Views
# ---------------------------------------------------------------------------

class RegisterView(APIView):
    """Register a new user and return JWT tokens.

    POST /api/auth/register/
    Body: { "email": "...", "phone": "...", "name": "...", "password": "...", "password_confirm": "..." }
    """

    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = UserRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        refresh = RefreshToken.for_user(user)
        return Response({
            "user": {
                "email": user.email,
                "phone": user.phone,
                "name": user.name,
            },
            "refresh": str(refresh),
            "access": str(refresh.access_token),
        }, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    """Login with email or phone + password, return JWT tokens.

    POST /api/auth/login/
    Body: { "email": "...", "password": "..." }  OR  { "phone": "...", "password": "..." }
    """

    permission_classes = [AllowAny]

    def post(self, request: Request) -> Response:
        serializer = TokenObtainPairSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response(serializer.validated_data, status=status.HTTP_200_OK)


class MeView(APIView):
    """Return the current authenticated user's profile.

    GET /api/auth/me/
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        serializer = UserSerializer(request.user)
        return Response(serializer.data)


class LogoutView(APIView):
    """Blacklist the refresh token to log out.

    POST /api/auth/logout/
    Body: { "refresh": "..." }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        try:
            refresh = RefreshToken(request.data.get("refresh"))
            refresh.blacklist()
            return Response({"detail": "Successfully logged out."}, status=status.HTTP_200_OK)
        except (TokenError, AttributeError):
            return Response(
                {"error": "Invalid refresh token."},
                status=status.HTTP_400_BAD_REQUEST,
            )


# ---------------------------------------------------------------------------
# Existing Personalization Views (unchanged)
# ---------------------------------------------------------------------------

class InteractionViewSet(viewsets.ModelViewSet):
    """API for recording and querying user interactions.

    Endpoints:
        POST /api/interactions/          — Record an interaction
        GET  /api/interactions/          — List interactions (optional ?session_id=)

    Query parameters:
        session_id: Filter interactions by session (required for GET).
    """

    serializer_class = UserInteractionSerializer
    permission_classes = [AllowAny]
    pagination_class = None

    def get_queryset(self):
        """Return interactions, optionally filtered by session_id.

        Args:
            request: The incoming DRF request.

        Returns:
            QuerySet of UserInteraction ordered by most recent first.
        """
        qs = UserInteraction.objects.select_related(
            "cluster", "cluster__primary_article",
            "cluster__primary_article__source",
            "cluster__primary_article__source__category",
        ).all()
        session_id = self.request.query_params.get("session_id")
        if session_id:
            qs = qs.filter(session_id=session_id)
        return qs

    def create(self, request: Request, *args, **kwargs) -> Response:
        """Record a user interaction (click, save, or dwell).

        Accepts JSON body:
            {
                "interaction_type": "click",   // "click" | "save" | "dwell"
                "cluster_id": 42,              // ID of the TopicCluster
                "dwell_seconds": 0             // only for "dwell" type
            }

        If ``session_id`` is not provided, one is generated.

        Args:
            request: DRF request with interaction data.

        Returns:
            201 with the created interaction serialized.
        """
        session_id = _get_session_id(request)
        data = request.data.copy()
        data["session_id"] = session_id

        # Validate cluster exists
        cluster_id = data.get("cluster_id")
        if cluster_id:
            try:
                TopicCluster.objects.get(id=cluster_id)
            except TopicCluster.DoesNotExist:
                return Response(
                    {"error": f"Cluster {cluster_id} not found"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    @action(detail=False, url_path="by-session", url_name="by-session")
    def by_session(self, request: Request) -> Response:
        """List all interactions for a given session.

        GET /api/interactions/by-session/?session_id=<uuid>
        """
        session_id = request.query_params.get("session_id")
        if not session_id:
            return Response(
                {"error": "session_id query param is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        interactions = self.get_queryset().filter(session_id=session_id)
        page = self.paginate_queryset(interactions)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(interactions, many=True)
        return Response(serializer.data)


class AffinityViewSet(viewsets.ViewSet):
    """API for computing and returning topic affinity profiles.

    Endpoints:
        GET /api/affinity/           — Current affinity scores per tab
        GET /api/affinity/history/   — How affinity has changed over time

    Query parameters:
        session_id: Session to compute affinity for (required).
        hours: Lookback window in hours (default 168 = 7 days).
    """

    permission_classes = [AllowAny]

    def list(self, request: Request) -> Response:
        """Compute topic affinity scores for a session.

        Affinity per tab = sum of (interaction_weight × decay_factor)
        for all interactions in the lookback window.

        GET /api/affinity/?session_id=<uuid>&hours=168

        Args:
            request: DRF request with session_id and optional hours param.

        Returns:
            200 with affinity scores per tab, sorted by score descending.
        """
        session_id = request.query_params.get("session_id")
        if not session_id:
            return Response(
                {"error": "session_id query param is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        hours = float(request.query_params.get("hours", 168))
        cutoff = django_tz.now() - timedelta(hours=hours)

        interactions = UserInteraction.objects.filter(
            session_id=session_id,
            created_at__gte=cutoff,
        ).select_related(
            "cluster__primary_article__source__category",
        )

        # Calculate affinity per tab
        affinity = {}
        now = django_tz.now()
        for interaction in interactions:
            category = interaction.cluster.primary_article.source.category
            hours_old = (now - interaction.created_at).total_seconds() / 3600
            weight = _INTERACTION_WEIGHTS.get(interaction.interaction_type, 1.0)
            decay = _decay_factor(hours_old)
            tab_slug = category.slug

            if tab_slug not in affinity:
                affinity[tab_slug] = {
                    "tab": tab_slug,
                    "tab_name": category.name,
                    "score": 0.0,
                    "interactions": 0,
                    "clicks": 0,
                    "saves": 0,
                }
            affinity[tab_slug]["score"] += weight * decay
            affinity[tab_slug]["interactions"] += 1
            if interaction.interaction_type == "click":
                affinity[tab_slug]["clicks"] += 1
            elif interaction.interaction_type == "save":
                affinity[tab_slug]["saves"] += 1

        # Normalize scores to 0–1 range
        max_score = max((v["score"] for v in affinity.values()), default=1.0)
        if max_score > 0:
            for v in affinity.values():
                v["score"] = round(v["score"] / max_score, 4)

        result = sorted(affinity.values(), key=lambda x: x["score"], reverse=True)
        return Response(result)

    @action(detail=False, url_path="history", url_name="history")
    def history(self, request: Request) -> Response:
        """Show how affinity scores have evolved over time.

        Buckets interactions into daily windows and shows affinity
        per tab per day.

        GET /api/affinity/history/?session_id=<uuid>&days=30

        Args:
            request: DRF request with session_id and optional days param.

        Returns:
            200 with a list of daily affinity snapshots.
        """
        session_id = request.query_params.get("session_id")
        if not session_id:
            return Response(
                {"error": "session_id query param is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        days = int(request.query_params.get("days", 30))
        cutoff = django_tz.now() - timedelta(days=days)

        interactions = UserInteraction.objects.filter(
            session_id=session_id,
            created_at__gte=cutoff,
        ).select_related(
            "cluster__primary_article__source__category",
        ).order_by("created_at")

        # Bucket by day
        daily: dict[str, dict[str, dict]] = {}
        for interaction in interactions:
            day_key = interaction.created_at.date().isoformat()
            if day_key not in daily:
                daily[day_key] = {}

            tab_slug = interaction.cluster.primary_article.source.category.slug
            weight = _INTERACTION_WEIGHTS.get(interaction.interaction_type, 1.0)

            if tab_slug not in daily[day_key]:
                daily[day_key][tab_slug] = {"score": 0.0, "interactions": 0}
            daily[day_key][tab_slug]["score"] += weight
            daily[day_key][tab_slug]["interactions"] += 1

        # Normalize each day
        result = []
        for day_key in sorted(daily.keys()):
            day_data = daily[day_key]
            max_s = max((v["score"] for v in day_data.values()), default=1.0)
            if max_s > 0:
                for v in day_data.values():
                    v["score"] = round(v["score"] / max_s, 4)
            result.append({
                "date": day_key,
                "tabs": day_data,
            })

        return Response(result)


class PersonalizedClusterViewSet(viewsets.ReadOnlyModelViewSet):
    """Personalized ("Just For You") cluster feed.

    Re-ranks clusters using topic affinity derived from user interactions,
    combined with recency decay.

    Endpoints:
        GET /api/clusters/personalized/   — Affinity-ranked feed

    Query parameters:
        session_id: Session to compute affinity for (required).
        tab: Filter by tab slug (optional).
        hours: Lookback window for affinity calculation (default 168h).
        ordering: 'affinity' (default), 'recency', or 'mixed'.
    """

    serializer_class = TopicClusterSerializer
    permission_classes = [AllowAny]

    def list(self, request: Request) -> Response:
        """Return clusters ranked by personalization affinity.

        Ranking formula:
            rank_score = (affinity_score × 0.7) + (recency_bonus × 0.3)

        Where:
            affinity_score = normalized sum of weighted interactions
            recency_bonus  = bonus for clusters published within 24h

        GET /api/clusters/personalized/?session_id=<uuid>&tab=india&hours=168

        Args:
            request: DRF request with session_id and optional params.

        Returns:
            Paginated response with clusters and computed rank scores.
        """
        session_id = _get_session_id(request)
        hours = float(request.query_params.get("hours", 168))
        cutoff = django_tz.now() - timedelta(hours=hours)

        # Build affinity profile
        interactions = UserInteraction.objects.filter(
            session_id=session_id,
            created_at__gte=cutoff,
        ).select_related(
            "cluster__primary_article__source__category",
        )

        affinity = {}
        now = django_tz.now()
        for interaction in interactions:
            category = interaction.cluster.primary_article.source.category
            hours_old = (now - interaction.created_at).total_seconds() / 3600
            weight = _INTERACTION_WEIGHTS.get(interaction.interaction_type, 1.0)
            decay = _decay_factor(hours_old)
            tab_slug = category.slug

            affinity[tab_slug] = affinity.get(tab_slug, 0.0) + weight * decay

        # Normalize affinity scores
        max_affinity = max(affinity.values(), default=1.0)
        if max_affinity > 0:
            for k in affinity:
                affinity[k] = affinity[k] / max_affinity

        # Get all clusters (with optional tab filter)
        tab = request.query_params.get("tab")
        qs = TopicCluster.objects.select_related(
            "primary_article",
            "primary_article__source",
            "primary_article__source__category",
        ).all()
        if tab:
            qs = qs.filter(primary_article__source__category__slug=tab)

        # Compute rank scores
        ranked_items = []
        for cluster in qs:
            category_slug = cluster.primary_article.source.category.slug
            affinity_score = affinity.get(category_slug, 0.0)

            # Recency bonus: clusters published in last 24h get up to 0.3
            pub_at = cluster.primary_article.published_at
            if pub_at:
                hours_since = (now - pub_at).total_seconds() / 3600
                if hours_since < _RECENTNESS_WINDOW_HOURS:
                    recency_bonus = _RECENTNESS_BONUS_MAX * (
                        1 - hours_since / _RECENTNESS_WINDOW_HOURS
                    )
                else:
                    recency_bonus = 0.0
            else:
                recency_bonus = 0.0

            # Combined rank score
            rank_score = round(affinity_score * 0.7 + recency_bonus * 0.3, 4)

            ranked_items.append({
                "cluster_data": TopicClusterSerializer(cluster).data,
                "rank_score": rank_score,
                "category": category_slug,
            })

        # Sort by rank_score descending
        ranked_items.sort(key=lambda x: x["rank_score"], reverse=True)

        # Pagination
        page_size = int(request.query_params.get("page_size", 20))
        page_num = int(request.query_params.get("page", 1))
        start = (page_num - 1) * page_size
        end = start + page_size
        page_items = ranked_items[start:end]

        return Response({
            "count": len(ranked_items),
            "next": f"?page={page_num + 1}&page_size={page_size}" if end < len(ranked_items) else None,
            "previous": f"?page={page_num - 1}&page_size={page_size}" if page_num > 1 else None,
            "results": page_items,
            "affinity_profile": {k: round(v, 4) for k, v in sorted(affinity.items(), key=lambda x: x[1], reverse=True)},
        })
