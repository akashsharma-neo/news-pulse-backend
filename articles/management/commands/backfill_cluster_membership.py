"""Backfill Article.topic_cluster for existing TopicClusters."""

from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from articles.models import Article, TopicCluster
from worker.tasks import _title_similarity


class Command(BaseCommand):
    help = (
        "Link articles to existing TopicClusters via topic_cluster FK. "
        "Always sets primary_article; optionally attaches similar articles in the same tab."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print counts without writing.",
        )
        parser.add_argument(
            "--similarity",
            type=float,
            default=0.35,
            help="Minimum title similarity for attaching non-primary members (default 0.35).",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        threshold = options["similarity"]
        linked_primary = 0
        linked_members = 0

        for cluster in TopicCluster.objects.select_related(
            "primary_article",
            "primary_article__source",
            "primary_article__source__category",
        ).iterator():
            primary = cluster.primary_article
            if not primary:
                continue

            if primary.topic_cluster_id != cluster.pk:
                if not dry_run:
                    primary.topic_cluster = cluster
                    primary.save(update_fields=["topic_cluster"])
                linked_primary += 1

            if not primary.source or not primary.source.category_id:
                continue

            window_start = (primary.published_at or primary.fetched_at) - timedelta(hours=72)
            candidates = Article.objects.filter(
                source__category_id=primary.source.category_id,
                published_at__gte=window_start,
                topic_cluster__isnull=True,
            ).exclude(pk=primary.pk)

            for candidate in candidates:
                if _title_similarity(primary.title, candidate.title) < threshold:
                    continue
                if not dry_run:
                    candidate.topic_cluster = cluster
                    candidate.save(update_fields=["topic_cluster"])
                linked_members += 1

        verb = "Would link" if dry_run else "Linked"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} primary on {linked_primary} cluster(s); "
                f"{verb.lower()} {linked_members} additional member article(s)."
            )
        )
