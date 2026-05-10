"""
NewsPulse digest serializers.
"""

from rest_framework import serializers

from .models import EmailSubscriber


class EmailSubscriberSerializer(serializers.ModelSerializer):
    """Serialize an email subscriber for API responses."""

    class Meta:
        model = EmailSubscriber
        fields = ["email", "is_active", "tabs", "created_at"]
        read_only_fields = ["email", "is_active", "tabs", "created_at"]


class SubscribeSerializer(serializers.Serializer):
    """Validate subscription request data."""

    email = serializers.EmailField(
        required=True,
        help_text="Email address to subscribe",
    )
    tabs = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False,
        default=list,
        help_text="Preferred tabs (e.g. ['india', 'sports']). Defaults to all.",
    )


class UnsubscribeSerializer(serializers.Serializer):
    """Validate unsubscribe request data."""

    token = serializers.UUIDField(
        required=True,
        help_text="Unsubscribe token from the subscriber record",
    )
