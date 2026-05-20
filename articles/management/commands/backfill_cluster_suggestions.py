"""Backfill Nex suggested_prompts for clusters that already have summaries."""

from __future__ import annotations

from django.conf import settings
from django.core.management.base import BaseCommand

from articles.models import TopicCluster
from articles.nex_prompts import save_nex_prompts_for_cluster


class Command(BaseCommand):
    help = (
        "Generate suggested_prompts for TopicClusters with a summary but empty prompts. "
        "Uses the same LLM settings as summarization."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=50,
            help="Max clusters to process in one run (default 50).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List clusters that would be updated without calling the LLM.",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        dry_run = options["dry_run"]

        if not settings.SUMMARIZE_ENABLED and not dry_run:
            self.stderr.write(
                self.style.WARNING(
                    "SUMMARIZE_ENABLED is false; LLM calls may fail. Use --dry-run to inspect."
                )
            )

        qs = (
            TopicCluster.objects.exclude(summary="")
            .filter(suggested_prompts=[])
            .select_related("primary_article", "primary_article__source__category")
            .order_by("-created_at")[:limit]
        )

        if dry_run:
            count = qs.count()
            self.stdout.write(f"Dry run: would backfill up to {count} cluster(s).")
            for cluster in qs[:10]:
                self.stdout.write(f"  cluster {cluster.pk}: {cluster.primary_article.title[:60]}")
            return

        try:
            from openai import OpenAI

            client = OpenAI(
                api_key=settings.OPENAI_COMPATIBLE_API_KEY,
                base_url=settings.OPENAI_COMPATIBLE_BASE_URL,
            )
            model = settings.OPENAI_COMPATIBLE_MODEL
        except Exception as exc:
            self.stderr.write(self.style.ERROR(f"OpenAI client init failed: {exc}"))
            return

        updated = 0
        for cluster in qs:
            prompts = save_nex_prompts_for_cluster(cluster, client, model)
            if prompts:
                updated += 1
                self.stdout.write(
                    f"cluster {cluster.pk}: {prompts[0][:50]}… (+{len(prompts) - 1} more)"
                )

        self.stdout.write(self.style.SUCCESS(f"Backfilled Nex prompts on {updated} cluster(s)."))
