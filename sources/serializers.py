"""
NewsPulse source API serializers.

Maps Source model instances to JSON for API responses.
"""

from rest_framework import serializers
from articles.models import Source


class SourceSerializer(serializers.ModelSerializer):
    """Serialize a Source (news outlet) for API responses.

    Fields:
        id: Primary key.
        name: Source name (e.g. 'NDTV', 'BBC').
        url: Base URL or RSS feed URL.
        category: Foreign key to the Tab this source belongs to.
        source_type: Ingestion method ('web', 'rss', or 'api').
        active: Whether the source is currently active.
    """

    class Meta:
        model = Source
        fields = ["id", "name", "url", "category", "source_type", "active"]
        read_only_fields = ["id"]
