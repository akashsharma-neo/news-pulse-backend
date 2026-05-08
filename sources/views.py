"""
NewsPulse source API views.

Provides a read-only endpoint for listing active news sources.
"""

from rest_framework import viewsets
from articles.models import Source
from .serializers import SourceSerializer


class SourceViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only API for news sources.

    Endpoint:
        GET /api/sources/ — List all active sources

    Only returns sources where ``active=True``.
    """

    serializer_class = SourceSerializer
    queryset = Source.objects.filter(active=True)
