"""Tests for articles.cluster_summary helpers."""

import uuid
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from articles.cluster_summary import prune_content_before
from articles.models import Article, Source, Tab, TopicCluster
from chat.models import ChatMessage


class PruneContentBeforeTest(TestCase):
    def setUp(self):
        self.tab = Tab.objects.create(name="T", slug="t", order=1)
        self.source = Source.objects.create(
            name="S", url="https://example.com", category=self.tab,
        )
        self.cutoff = timezone.now() - timedelta(days=1)

    def _article(self, suffix: str, fetched_at) -> Article:
        article = Article.objects.create(
            title=f"Story {suffix}",
            url=f"https://example.com/{suffix}",
            source=self.source,
            published_at=fetched_at,
        )
        Article.objects.filter(pk=article.pk).update(fetched_at=fetched_at)
        article.refresh_from_db()
        return article

    def _cluster(self, primary: Article, created_at, summary: str = "summary") -> TopicCluster:
        cluster = TopicCluster.objects.create(
            topic_id=uuid.uuid4(),
            primary_article=primary,
            summary=summary,
        )
        TopicCluster.objects.filter(pk=cluster.pk).update(created_at=created_at)
        cluster.refresh_from_db()
        return cluster

    def test_deletes_old_clusters_and_articles(self):
        old_fetched = self.cutoff - timedelta(hours=2)
        old_article = self._article("old", old_fetched)
        self._cluster(old_article, created_at=self.cutoff - timedelta(hours=1))

        new_fetched = self.cutoff + timedelta(hours=1)
        new_article = self._article("new", new_fetched)
        self._cluster(new_article, created_at=self.cutoff + timedelta(hours=1))

        result = prune_content_before(self.cutoff)

        self.assertEqual(result["clusters_deleted"], 1)
        self.assertEqual(result["articles_deleted"], 1)
        self.assertEqual(TopicCluster.objects.count(), 1)
        self.assertEqual(Article.objects.count(), 1)

    def test_keeps_cluster_when_primary_article_is_old_but_cluster_is_new(self):
        """Regression: Article CASCADE must not drop clusters created after cutoff."""
        old_fetched = self.cutoff - timedelta(hours=5)
        primary = self._article("stale-primary", old_fetched)
        kept = self._cluster(
            primary,
            created_at=self.cutoff + timedelta(hours=2),
            summary="keep me",
        )

        result = prune_content_before(self.cutoff)

        self.assertEqual(result["clusters_deleted"], 0)
        self.assertEqual(result["articles_deleted"], 0)
        self.assertTrue(TopicCluster.objects.filter(pk=kept.pk).exists())
        self.assertTrue(Article.objects.filter(pk=primary.pk).exists())

    def test_cluster_delete_count_excludes_cascade_chat_messages(self):
        old_fetched = self.cutoff - timedelta(hours=2)
        article = self._article("with-chat", old_fetched)
        cluster = self._cluster(article, created_at=self.cutoff - timedelta(hours=1))
        ChatMessage.objects.create(cluster=cluster, role="user", content="hello")

        result = prune_content_before(self.cutoff)

        self.assertEqual(result["clusters_deleted"], 1)
        self.assertEqual(ChatMessage.objects.count(), 0)
