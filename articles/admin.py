"""
NewsPulse Django admin configuration.

Registers Tab, Source, Article, and TopicCluster with custom list displays,
filters, and search for operational use.
"""

from django.contrib import admin
from .models import Tab, Source, Article, TopicCluster


@admin.register(Tab)
class TabAdmin(admin.ModelAdmin):
    """Admin for news category tabs.

    Features:
        - Auto-populate slug from name
        - List view with name, slug, and order columns
    """

    list_display = ("name", "slug", "order")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Source)
class SourceAdmin(admin.ModelAdmin):
    """Admin for news sources.

    Features:
        - Filter by category, source type, and active status
        - List view with source name, category, type, and active flag
    """

    list_display = ("name", "category", "source_type", "active")
    list_filter = ("category", "source_type", "active")


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    """Admin for articles.

    Features:
        - Search by title and URL
        - Filter by source category
        - List view with title, source, published date, and fetch time
    """

    list_display = ("title", "source", "published_at", "fetched_at")
    list_filter = ("source__category",)
    search_fields = ("title", "url")


@admin.register(TopicCluster)
class TopicClusterAdmin(admin.ModelAdmin):
    """Admin for topic clusters.

    Features:
        - Search by summary text
        - Filter by creation date
        - List preview of summary (truncated to 80 chars)
    """

    list_display = ("primary_article", "summary_preview", "created_at")
    search_fields = ("summary",)
    list_filter = ("created_at",)

    def summary_preview(self, obj: TopicCluster) -> str:
        """Return a truncated preview of the cluster summary.

        Args:
            obj: The TopicCluster instance.

        Returns:
            First 80 characters of the summary, truncated with '...' if longer.
        """
        return obj.summary[:80] + "..." if len(obj.summary) > 80 else obj.summary

    summary_preview.short_description = "Summary"
