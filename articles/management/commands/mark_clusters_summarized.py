"""Mark TopicClusters with empty summary as summarized (skip future LLM runs)."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from articles.models import TopicCluster
from worker.article_content import fallback_summary_from_article


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
        qs = TopicCluster.objects.filter(summary="").select_related(
            "primary_article",
        )

        updated = 0
        for cluster in qs.iterator():
            summary = fallback_summary_from_article(cluster.primary_article)
            if dry_run:
                updated += 1
                continue
            cluster.summary = summary
            cluster.save(update_fields=["summary"])
            updated += 1

        verb = "Would update" if dry_run else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{verb} {updated} cluster(s)."))
