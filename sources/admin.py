"""
NewsPulse source admin configuration.

Registers ScraperConfig in Django admin for operational management
of scraper settings per source.
"""

from django.contrib import admin

from core.admin_mixins import TotalCountChangeListMixin
from .models import ScraperConfig


@admin.register(ScraperConfig)
class ScraperConfigAdmin(TotalCountChangeListMixin, admin.ModelAdmin):
    """Admin for scraper configuration.

    Features:
        - Inline editing of CSS selectors and headers
        - Toggle enabled/disabled per source
        - List view with source name
    """

    list_display = ("source", "enabled")
    list_filter = ("enabled",)
    readonly_fields = ("source",)
