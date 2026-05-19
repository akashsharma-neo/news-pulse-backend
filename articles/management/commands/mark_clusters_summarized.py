"""Mark TopicClusters with empty summary as summarized (skip future LLM runs)."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from articles.cluster_summary import mark_pending_cluster_summaries
from articles.models import TopicCluster


class Command(BaseCommand):
    help = (
        "Fill empty TopicCluster.summary from the primary article preview so "
        "summarize_clusters skips them (no OpenAI calls)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print how many would be updated without writing.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        pending = TopicCluster.objects.filter(summary="").count()
        if dry_run:
            self.stdout.write(self.style.SUCCESS(f"Would update {pending} cluster(s)."))
            return

        updated = mark_pending_cluster_summaries()
        self.stdout.write(self.style.SUCCESS(f"Updated {updated} cluster(s)."))
