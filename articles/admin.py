"""
NewsPulse Django admin configuration.

Registers Tab, Source, Article, and TopicCluster with custom list displays,
filters, and search for operational use.
"""

from datetime import timedelta

from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.urls import path, reverse
from django.utils import timezone

from core.admin_mixins import TotalCountChangeListMixin
from .models import Tab, Source, Article, TopicCluster


@admin.register(Tab)
class TabAdmin(TotalCountChangeListMixin, admin.ModelAdmin):
    """Admin for news category tabs.

    Features:
        - Auto-populate slug from name
        - List view with name, slug, and order columns
    """

    list_display = ("name", "slug", "order")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Source)
class SourceAdmin(TotalCountChangeListMixin, admin.ModelAdmin):
    """Admin for news sources.

    Features:
        - Filter by category, source type, and active status
        - List view with source name, category, type, and active flag
    """

    list_display = ("name", "category", "source_type", "active")
    list_filter = ("category", "source_type", "active")


@admin.register(Article)
class ArticleAdmin(TotalCountChangeListMixin, admin.ModelAdmin):
    """Admin for articles.

    Features:
        - Search by title and URL
        - Filter by source category
        - List view with title, source, published date, and fetch time
        - Run scrape action and pipeline totals on changelist
    """

    list_display = ("title", "source", "published_at", "fetched_at")
    list_filter = ("source__category",)
    search_fields = ("title", "url")
    change_list_template = "admin/articles/article/change_list.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "run-scrape/",
                self.admin_site.admin_view(self.run_scrape_view),
                name="articles_article_run_scrape",
            ),
            path(
                "run-cluster/",
                self.admin_site.admin_view(self.run_cluster_view),
                name="articles_article_run_cluster",
            ),
        ]
        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        cutoff = timezone.now() - timedelta(hours=48)
        primary_ids = TopicCluster.objects.values_list("primary_article_id", flat=True)
        unclustered_48h = Article.objects.filter(
            fetched_at__gte=cutoff,
        ).exclude(pk__in=primary_ids).count()
        extra_context["pipeline_stats"] = {
            "articles": Article.objects.count(),
            "sources_total": Source.objects.count(),
            "sources_active": Source.objects.filter(active=True).count(),
            "topic_clusters": TopicCluster.objects.count(),
            "unclustered_48h": unclustered_48h,
            "tabs": Tab.objects.count(),
        }
        return super().changelist_view(request, extra_context)

    def run_scrape_view(self, request):
        changelist_url = reverse("admin:articles_article_changelist")

        if request.method != "POST":
            return HttpResponseRedirect(changelist_url)

        if not self.has_change_permission(request):
            messages.error(request, "You do not have permission to run scraping.")
            return HttpResponseRedirect(changelist_url)

        active_count = Source.objects.filter(active=True).count()
        if active_count == 0:
            messages.warning(
                request,
                "No active sources configured. Enable sources before scraping.",
            )
            return HttpResponseRedirect(changelist_url)

        try:
            from worker.tasks import scrape_sources

            result = scrape_sources.delay()
            messages.success(
                request,
                f"Scrape queued for {active_count} active source(s). "
                f"Task id: {result.id}",
            )
        except Exception as exc:
            messages.error(
                request,
                f"Failed to queue scrape: {exc}. "
                "Ensure the Celery worker and Redis broker are running.",
            )

        return HttpResponseRedirect(changelist_url)

    def run_cluster_view(self, request):
        changelist_url = reverse("admin:articles_article_changelist")

        if request.method != "POST":
            return HttpResponseRedirect(changelist_url)

        if not self.has_change_permission(request):
            messages.error(request, "You do not have permission to run clustering.")
            return HttpResponseRedirect(changelist_url)

        try:
            from worker.tasks import cluster_and_summarize

            result = cluster_and_summarize.delay()
            messages.success(
                request,
                f"Cluster articles queued. Task id: {result.id}",
            )
        except Exception as exc:
            messages.error(
                request,
                f"Failed to queue clustering: {exc}. "
                "Ensure the Celery worker and Redis broker are running.",
            )

        return HttpResponseRedirect(changelist_url)


@admin.register(TopicCluster)
class TopicClusterAdmin(TotalCountChangeListMixin, admin.ModelAdmin):
    """Admin for topic clusters.

    Features:
        - Search by summary text
        - Filter by creation date
        - List preview of summary (truncated to 80 chars)
        - Summarize clusters action on changelist
    """

    list_display = ("primary_article", "summary_preview", "created_at")
    search_fields = ("summary",)
    list_filter = ("created_at",)
    change_list_template = "admin/articles/topiccluster/change_list.html"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "summarize-clusters/",
                self.admin_site.admin_view(self.summarize_clusters_view),
                name="articles_topiccluster_summarize_clusters",
            ),
        ]
        return custom_urls + urls

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["pending_summaries"] = TopicCluster.objects.filter(
            summary=""
        ).count()
        return super().changelist_view(request, extra_context)

    def summarize_clusters_view(self, request):
        changelist_url = reverse("admin:articles_topiccluster_changelist")

        if request.method != "POST":
            return HttpResponseRedirect(changelist_url)

        if not self.has_change_permission(request):
            messages.error(
                request, "You do not have permission to run summarization."
            )
            return HttpResponseRedirect(changelist_url)

        pending = TopicCluster.objects.filter(summary="").count()
        if pending == 0:
            messages.info(request, "No clusters with empty summaries.")
            return HttpResponseRedirect(changelist_url)

        try:
            from worker.tasks import summarize_clusters

            result = summarize_clusters.delay()
            messages.success(
                request,
                f"Summarize clusters queued ({pending} pending). "
                f"Task id: {result.id}",
            )
        except Exception as exc:
            messages.error(
                request,
                f"Failed to queue summarization: {exc}. "
                "Ensure the Celery worker and Redis broker are running.",
            )

        return HttpResponseRedirect(changelist_url)

    def summary_preview(self, obj: TopicCluster) -> str:
        """Return a truncated preview of the cluster summary.

        Args:
            obj: The TopicCluster instance.

        Returns:
            First 80 characters of the summary, truncated with '...' if longer.
        """
        return obj.summary[:80] + "..." if len(obj.summary) > 80 else obj.summary

    summary_preview.short_description = "Summary"
