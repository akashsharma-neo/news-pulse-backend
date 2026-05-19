"""Tests for article serializers — Tab, Article, TopicCluster."""

from django.test import TestCase
from django.utils import timezone
from articles.models import Tab, Source, Article, TopicCluster


def word_count(text: str) -> int:
    return len(text.split())


class TabSerializerTest(TestCase):
    def setUp(self):
        self.tab = Tab.objects.create(name="India", slug="india", order=1)

    def test_tab_serializer_fields(self):
        from articles.serializers import TabSerializer
        data = TabSerializer(self.tab).data
        self.assertEqual(data["id"], self.tab.id)
        self.assertEqual(data["name"], "India")
        self.assertEqual(data["slug"], "india")
        self.assertEqual(data["order"], 1)


class ArticleSerializerTest(TestCase):
    def setUp(self):
        self.tab = Tab.objects.create(name="Global", slug="global", order=1)
        self.source = Source.objects.create(
            name="BBC", url="https://bbc.com/feed",
            category=self.tab, source_type="rss",
        )
        self.article = Article.objects.create(
            title="Test Article",
            url="https://bbc.com/story",
            source=self.source,
            published_at=timezone.now(),
            summary="A quick summary.",
            source_image_url="https://cdn.bbc.com/img.jpg",
        )

    def test_article_serializer_fields(self):
        from articles.serializers import ArticleSerializer
        data = ArticleSerializer(self.article).data
        self.assertEqual(data["title"], "Test Article")
        self.assertEqual(data["source_name"], "BBC")
        self.assertEqual(data["category_slug"], "global")
        self.assertEqual(data["summary"], "A quick summary.")
        self.assertEqual(data["source_image_url"], "https://cdn.bbc.com/img.jpg")
        self.assertIn("published_at", data)
        self.assertIn("id", data)
        self.assertIn("url", data)


class TopicClusterSerializerTest(TestCase):
    def setUp(self):
        self.tab = Tab.objects.create(name="Sports", slug="sports", order=1)
        self.source = Source.objects.create(
            name="ESPN", url="https://espn.com/feed",
            category=self.tab, source_type="rss",
        )
        self.article = Article.objects.create(
            title="Match Report",
            url="https://espn.com/match",
            source=self.source,
            published_at=timezone.now(),
            full_text="This is a full article body with sufficient words for testing the summary truncation logic in the serializer method field.",
            summary="",
        )
        self.cluster = TopicCluster.objects.create(
            topic_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
            primary_article=self.article,
            summary="An AI-generated digest summary for the cluster.",
            sources=["ESPN", "Sportskeeda"],
        )

    def test_cluster_serializer_returns_llm_summary(self):
        from articles.serializers import TopicClusterSerializer
        data = TopicClusterSerializer(self.cluster).data
        self.assertEqual(data["summary"], "An AI-generated digest summary for the cluster.")

    def test_cluster_serializer_fallback_to_article_summary(self):
        from articles.serializers import TopicClusterSerializer
        self.cluster.summary = ""
        self.cluster.save()
        self.article.summary = "A short article-level summary."
        self.article.save()
        data = TopicClusterSerializer(self.cluster).data
        self.assertEqual(data["summary"], "A short article-level summary.")

    def test_cluster_serializer_fallback_to_full_text(self):
        from articles.serializers import TopicClusterSerializer
        self.cluster.summary = ""
        self.cluster.save()
        self.article.summary = ""
        self.article.save()
        data = TopicClusterSerializer(self.cluster).data
        self.assertIn("full article body", data["summary"])

    def test_cluster_serializer_fallback_to_title(self):
        from articles.serializers import TopicClusterSerializer
        self.cluster.summary = ""
        self.cluster.save()
        self.article.summary = ""
        self.article.full_text = ""
        self.article.save()
        data = TopicClusterSerializer(self.cluster).data
        self.assertEqual(data["summary"], "Match Report")

    def test_cluster_serializer_truncates_long_text(self):
        from articles.serializers import TopicClusterSerializer
        self.cluster.summary = ""
        self.cluster.save()
        self.article.summary = ""
        self.article.full_text = " ".join(["word"] * 200)
        self.article.save()
        data = TopicClusterSerializer(self.cluster).data
        self.assertLess(word_count(data["summary"]), 200)
        self.assertGreater(word_count(data["summary"]), 50)

    def test_cluster_serializer_source_names(self):
        from articles.serializers import TopicClusterSerializer
        data = TopicClusterSerializer(self.cluster).data
        self.assertEqual(data["source_names"], ["ESPN", "Sportskeeda"])

    def test_cluster_serializer_denormalized_fields(self):
        from articles.serializers import TopicClusterSerializer
        data = TopicClusterSerializer(self.cluster).data
        self.assertEqual(data["primary_title"], "Match Report")
        self.assertEqual(data["source_name"], "ESPN")
        self.assertEqual(data["category_slug"], "sports")
        self.assertEqual(data["primary_url"], "https://espn.com/match")
        self.assertIn("published_at", data)
        self.assertIn("created_at", data)
        self.assertIn("topic_id", data)
