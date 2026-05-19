"""Tests for feed duplicate cluster detection and merge."""

import uuid
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from articles.cluster_dedup import (
    dedupe_clusters_for_tab,
    find_matching_topic_cluster,
    merge_articles_into_cluster,
)
from articles.models import Article, Source, Tab, TopicCluster
from articles.url_utils import article_exists_for_url, normalize_article_url
from worker.tasks import _title_similarity


class ArticleUrlDedupTests(TestCase):
    def setUp(self):
        self.tab = Tab.objects.create(name="T", slug="t", order=1)
        self.source = Source.objects.create(
            name="S", url="https://example.com", category=self.tab,
        )

    def test_article_exists_for_normalized_match(self):
        Article.objects.create(
            title="A",
            url="https://example.com/story",
            source=self.source,
            published_at=timezone.now(),
        )
        self.assertTrue(
            article_exists_for_url("https://www.example.com/story/?utm_source=x")
        )

    def test_normalize_stored_on_scrape_path(self):
        url = normalize_article_url("https://WWW.Example.com/x/?utm_campaign=y")
        self.assertEqual(url, "https://example.com/x")


class ClusterDedupTests(TestCase):
    def setUp(self):
        self.tab = Tab.objects.create(name="India", slug="india", order=1)
        self.source = Source.objects.create(
            name="NDTV", url="https://ndtv.com", category=self.tab,
        )
        self.article1 = Article.objects.create(
            title="PM visits flood-hit region in Assam",
            url="https://ndtv.com/1",
            source=self.source,
            full_text="Prime Minister visited Assam flood areas today.",
            published_at=timezone.now(),
        )
        self.cluster1 = TopicCluster.objects.create(
            topic_id=uuid.uuid4(),
            primary_article=self.article1,
            summary="Existing summary",
            sources=["NDTV"],
        )
        self.article1.topic_cluster = self.cluster1
        self.article1.save(update_fields=["topic_cluster"])

    def test_find_matching_topic_cluster(self):
        article2 = Article.objects.create(
            title="PM visits flood hit Assam region",
            url="https://other.com/2",
            source=self.source,
            full_text="Prime Minister visited Assam flood areas.",
            published_at=timezone.now(),
        )
        match = find_matching_topic_cluster(
            article2,
            category_slug="india",
            title_similarity=_title_similarity,
        )
        self.assertEqual(match.pk, self.cluster1.pk)

    def test_merge_articles_into_cluster(self):
        article2 = Article.objects.create(
            title="Related",
            url="https://other.com/2",
            source=self.source,
            published_at=timezone.now() + timedelta(hours=1),
        )
        merge_articles_into_cluster(self.cluster1, [article2])
        article2.refresh_from_db()
        self.cluster1.refresh_from_db()
        self.assertEqual(article2.topic_cluster_id, self.cluster1.pk)
        self.assertEqual(self.cluster1.primary_article_id, article2.pk)

    def test_dedupe_clusters_for_tab(self):
        article2 = Article.objects.create(
            title="PM visits flood hit Assam region",
            url="https://other.com/2",
            source=self.source,
            full_text="Prime Minister visited Assam flood areas.",
            published_at=timezone.now(),
        )
        cluster2 = TopicCluster.objects.create(
            topic_id=uuid.uuid4(),
            primary_article=article2,
            summary="Dup summary",
            sources=["Other"],
        )
        article2.topic_cluster = cluster2
        article2.save(update_fields=["topic_cluster"])

        result = dedupe_clusters_for_tab(
            "india", title_similarity=_title_similarity,
        )
        self.assertEqual(result["clusters_deleted"], 1)
        remaining = TopicCluster.objects.get()
        self.assertEqual(TopicCluster.objects.count(), 1)
        self.assertEqual(Article.objects.filter(topic_cluster=remaining).count(), 2)
