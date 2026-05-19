"""Re-clean Article.full_text and optionally re-summarize affected clusters."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from articles.models import Article, TopicCluster
from worker.article_content import clean_article_text, is_usable_article_body


class Command(BaseCommand):
    help = (
        "Run clean_article_text on stored Article.full_text rows. "
        "Use --resummarize to clear cluster summaries and queue summarize_clusters."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            type=str,
            default="",
            help='Only process articles from this source name (e.g. "The Hindu").',
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report counts without writing.",
        )
        parser.add_argument(
            "--resummarize",
            action="store_true",
            help="Clear TopicCluster.summary for touched clusters and dispatch summarize_clusters.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        source_filter = (options["source"] or "").strip()
        resummarize = options["resummarize"]

        qs = Article.objects.select_related("source").all()
        if source_filter:
            qs = qs.filter(source__name=source_filter)

        updated = 0
        unusable = 0
        cluster_ids: set[int] = set()

        for article in qs.iterator():
            source_name = article.source.name if article.source else None
            cleaned = clean_article_text(article.full_text or "", source_name)
            if cleaned == (article.full_text or ""):
                continue
            if not is_usable_article_body(cleaned, source_name) and cleaned:
                unusable += 1
            if article.topic_cluster_id:
                cluster_ids.add(article.topic_cluster_id)
            if not dry_run:
                article.full_text = cleaned
                article.save(update_fields=["full_text"])
            updated += 1

        cleared = 0
        if resummarize and cluster_ids and not dry_run:
            cleared = TopicCluster.objects.filter(pk__in=cluster_ids).update(summary="")
            from worker.tasks import summarize_clusters
            summarize_clusters.delay()
        elif resummarize and cluster_ids and dry_run:
            cleared = len(cluster_ids)

        verb = "Would update" if dry_run else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{verb} {updated} article body/ies "
                f"({unusable} still low-quality after clean)."
            )
        )
        if resummarize:
            self.stdout.write(
                self.style.SUCCESS(
                    f"{'Would clear' if dry_run else 'Cleared'} summaries on "
                    f"{cleared} cluster(s)."
                )
            )
