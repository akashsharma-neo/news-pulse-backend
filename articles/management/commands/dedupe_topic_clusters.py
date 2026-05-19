"""Merge duplicate TopicCluster rows on the tab feed (same story, multiple cards)."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from articles.cluster_dedup import dedupe_clusters_for_tab
from articles.models import Tab
from worker.tasks import _title_similarity


class Command(BaseCommand):
    help = (
        "Merge TopicClusters in the same tab that cover the same story "
        "(title/content similarity). Run on prod after deploying feed dedup fixes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report merges without deleting duplicate clusters.",
        )
        parser.add_argument(
            "--tab",
            dest="tab_slug",
            default="",
            help="Only dedupe this tab slug (default: all tabs).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        tab_slug = (options["tab_slug"] or "").strip()

        tabs = Tab.objects.all()
        if tab_slug:
            tabs = tabs.filter(slug=tab_slug)
            if not tabs.exists():
                self.stderr.write(self.style.ERROR(f"Unknown tab slug: {tab_slug}"))
                return

        total_merged = 0
        total_deleted = 0
        for tab in tabs:
            result = dedupe_clusters_for_tab(
                tab.slug,
                title_similarity=_title_similarity,
                dry_run=dry_run,
            )
            total_merged += result["stories_merged"]
            total_deleted += result["clusters_deleted"]
            if result["clusters_deleted"] or result["stories_merged"]:
                verb = "Would merge" if dry_run else "Merged"
                self.stdout.write(
                    f"{tab.slug}: {verb} {result['stories_merged']} stor(ies), "
                    f"{'would delete' if dry_run else 'deleted'} "
                    f"{result['clusters_deleted']} duplicate cluster(s)"
                )

        if dry_run:
            self.stdout.write(
                self.style.WARNING(
                    f"Dry run: {total_merged} stor(ies) with duplicates, "
                    f"{total_deleted} cluster(s) would be removed."
                )
            )
        else:
            from worker.tasks import invalidate_cluster_feed_cache

            if total_deleted:
                invalidate_cluster_feed_cache()
            self.stdout.write(
                self.style.SUCCESS(
                    f"Done: merged {total_merged} stor(ies), "
                    f"deleted {total_deleted} duplicate cluster(s)."
                )
            )
