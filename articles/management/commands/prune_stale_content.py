"""Delete articles and topic clusters older than a cutoff (default: start of today)."""

from __future__ import annotations

from datetime import datetime

from django.core.management.base import BaseCommand
from django.utils import timezone

from articles.cluster_summary import prune_content_before, start_of_today


class Command(BaseCommand):
    help = (
        "Delete TopicCluster and Article rows before a cutoff "
        "(default: start of today in the active timezone)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print how many rows would be deleted without writing.",
        )
        parser.add_argument(
            "--before",
            type=str,
            default="today",
            help="Cutoff: 'today' (default) or ISO date YYYY-MM-DD.",
        )

    def handle(self, *args, **options):
        before = options["before"]
        if before == "today":
            cutoff = start_of_today()
        else:
            parsed = datetime.strptime(before, "%Y-%m-%d")
            cutoff = timezone.make_aware(
                parsed.replace(hour=0, minute=0, second=0, microsecond=0),
                timezone.get_current_timezone(),
            )

        from articles.models import Article, TopicCluster

        cluster_qs = TopicCluster.objects.filter(created_at__lt=cutoff)
        article_qs = Article.objects.filter(fetched_at__lt=cutoff)
        cluster_count = cluster_qs.count()
        article_count = article_qs.count()

        if options["dry_run"]:
            self.stdout.write(
                self.style.WARNING(
                    f"Would delete {cluster_count} cluster(s) and {article_count} article(s) "
                    f"before {cutoff.isoformat()}."
                )
            )
            return

        result = prune_content_before(cutoff)
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {result['clusters_deleted']} cluster(s) and "
                f"{result['articles_deleted']} article(s) before {cutoff.isoformat()}."
            )
        )
