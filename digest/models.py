"""
NewsPulse digest app models.

Models:
    EmailSubscriber — Users who have subscribed to daily email digests.
"""

import uuid

from django.db import models
from django.utils import timezone


class EmailSubscriber(models.Model):
    """Tracks users who have subscribed to daily email digests.

    Supports unsubscribing via a unique token. Stores preferred tabs so
    subscribers only receive digests for their topics of interest.
    """

    email = models.EmailField(
        max_length=254,
        unique=True,
        help_text="Email address for the daily digest",
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether the subscriber is currently active",
    )
    tabs = models.JSONField(
        default=list,
        blank=True,
        help_text="Preferred news tabs (e.g. ['india', 'sports'])",
    )
    unsubscribe_token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        help_text="Unique token for unsubscribe links",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the subscriber opted in",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="Last time the subscription was updated",
    )

    class Meta:
        db_table = "digest_email_subscriber"
        ordering = ["-created_at"]

    def __str__(self):
        return self.email
