"""Backfill TopicCluster.image_url from primary article or tab placeholders."""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db.models import Q

from articles.image_resolver import pick_cluster_image, resolve_cluster_display_image
from articles.models import TopicCluster


class Command(BaseCommand):
    help = (
        "Set image_url on clusters missing it, using primary article source_image_url "
        "or tab placeholder URLs (does not re-fetch RSS feeds)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--all",
            action="store_true",
            help="Recompute image_url for every cluster (not only empty image_url).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print changes without writing to the database.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        recompute_all = options["all"]

        qs = TopicCluster.objects.select_related(
            "primary_article",
            "primary_article__source",
            "primary_article__source__category",
        )
        if not recompute_all:
            qs = qs.filter(Q(image_url="") | Q(image_url__isnull=True))

        updated = 0
        for cluster in qs.iterator():
            primary = cluster.primary_article
            if not primary:
                continue

            category_slug = None
            if primary.source and primary.source.category:
                category_slug = primary.source.category.slug

            if recompute_all:
                new_url = resolve_cluster_display_image(cluster)
            else:
                new_url = pick_cluster_image([primary], primary, category_slug)

            if cluster.image_url == new_url:
                continue

            if dry_run:
                self.stdout.write(
                    f"Cluster {cluster.pk}: {cluster.image_url!r} -> {new_url!r}"
                )
            else:
                cluster.image_url = new_url[:2048]
                cluster.save(update_fields=["image_url"])

            updated += 1

        verb = "Would update" if dry_run else "Updated"
        self.stdout.write(self.style.SUCCESS(f"{verb} {updated} cluster(s)."))
