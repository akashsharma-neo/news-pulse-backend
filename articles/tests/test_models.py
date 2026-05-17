"""Tests for article domain models — Tab, Source, Article, TopicCluster."""

from django.test import TestCase
from django.utils import timezone
from articles.models import Tab, Source, Article, TopicCluster


class TabModelTest(TestCase):
    def setUp(self):
        self.tab = Tab.objects.create(name="India", slug="india", order=1)

    def test_tab_creation(self):
        self.assertEqual(self.tab.name, "India")
        self.assertEqual(self.tab.slug, "india")
        self.assertEqual(self.tab.order, 1)

    def test_tab_str(self):
        self.assertEqual(str(self.tab), "India")

    def test_tab_ordering(self):
        Tab.objects.create(name="Sports", slug="sports", order=2)
        Tab.objects.create(name="Business", slug="business", order=0)
        tabs = list(Tab.objects.all())
        self.assertEqual(tabs[0].slug, "business")
        self.assertEqual(tabs[1].slug, "india")
        self.assertEqual(tabs[2].slug, "sports")


class SourceModelTest(TestCase):
    def setUp(self):
        self.tab = Tab.objects.create(name="India", slug="india", order=1)
        self.source = Source.objects.create(
            name="Test Source",
            url="https://example.com/feed",
            category=self.tab,
            source_type="rss",
        )

    def test_source_creation(self):
        self.assertEqual(self.source.name, "Test Source")
        self.assertEqual(self.source.source_type, "rss")
        self.assertTrue(self.source.active)

    def test_source_str(self):
        self.assertIn("Test Source", str(self.source))
        self.assertIn("India", str(self.source))

    def test_source_defaults(self):
        source = Source.objects.create(
            name="Default Source",
            url="https://default.com",
            category=self.tab,
        )
        self.assertEqual(source.source_type, "web")
        self.assertTrue(source.active)

    def test_source_ordering(self):
        Source.objects.create(name="Z Source", url="https://z.com", category=self.tab)
        Source.objects.create(name="A Source", url="https://a.com", category=self.tab)
        sources = list(Source.objects.all())
        self.assertEqual(sources[0].name, "A Source")
        self.assertEqual(sources[-1].name, "Z Source")


class ArticleModelTest(TestCase):
    def setUp(self):
        self.tab = Tab.objects.create(name="Global", slug="global", order=1)
        self.source = Source.objects.create(
            name="BBC", url="https://bbc.com/feed", category=self.tab,
        )
        self.article = Article.objects.create(
            title="Test Headline",
            url="https://bbc.com/story",
            source=self.source,
            published_at=timezone.now(),
            full_text="Full article body text for testing purposes.",
        )

    def test_article_creation(self):
        self.assertEqual(self.article.title, "Test Headline")
        self.assertIsNotNone(self.article.published_at)
        self.assertIsNotNone(self.article.fetched_at)

    def test_article_str(self):
        self.assertEqual(str(self.article), "Test Headline")

    def test_article_ordering(self):
        later = Article.objects.create(
            title="Later", url="https://bbc.com/later",
            source=self.source,
            published_at=timezone.now(),
        )
        Article.objects.create(
            title="Earlier", url="https://bbc.com/earlier",
            source=self.source,
            published_at=timezone.now(),
        )
        articles = list(Article.objects.all())
        self.assertEqual(articles[0].title, "Earlier")
        self.assertEqual(articles[-1].title, "Test Headline")

    def test_article_defaults(self):
        article = Article.objects.create(
            title="Defaults", url="https://bbc.com/defaults",
            source=self.source,
        )
        self.assertEqual(article.full_text, "")
        self.assertEqual(article.summary, "")
        self.assertEqual(article.source_image_url, "")
        self.assertIsNone(article.published_at)

    def test_string_representation_truncated(self):
        article = Article.objects.create(
            title="A" * 200, url="https://bbc.com/long", source=self.source,
        )
        self.assertEqual(len(str(article)), 100)


class TopicClusterModelTest(TestCase):
    def setUp(self):
        self.tab = Tab.objects.create(name="Sports", slug="sports", order=1)
        self.source = Source.objects.create(
            name="ESPN", url="https://espn.com/feed", category=self.tab,
        )
        self.article = Article.objects.create(
            title="Match Report", url="https://espn.com/match",
            source=self.source, published_at=timezone.now(),
        )
        self.cluster = TopicCluster.objects.create(
            topic_id="12345678-1234-5678-1234-567812345678",
            primary_article=self.article,
            summary="A sports digest summary.",
            sources=["ESPN", "Sportskeeda"],
        )

    def test_cluster_creation(self):
        self.assertEqual(self.cluster.topic_id, "12345678-1234-5678-1234-567812345678")
        self.assertEqual(self.cluster.summary, "A sports digest summary.")
        self.assertEqual(self.cluster.sources, ["ESPN", "Sportskeeda"])

    def test_cluster_str(self):
        self.assertEqual(str(self.cluster), "Match Report")

    def test_cluster_source_names(self):
        self.assertEqual(self.cluster.source_names(), ["ESPN", "Sportskeeda"])

    def test_cluster_source_names_non_list(self):
        self.cluster.sources = "not a list"
        self.assertEqual(self.cluster.source_names(), [])

    def test_cluster_source_names_none(self):
        self.cluster.sources = None
        self.assertEqual(self.cluster.source_names(), [])

    def test_cluster_image_url_default(self):
        self.assertEqual(self.cluster.image_url, "")

    def test_cluster_ordering(self):
        cluster2 = TopicCluster.objects.create(
            topic_id="87654321-8765-4321-8765-432187654321",
            primary_article=self.article,
            summary="Later summary.",
        )
        clusters = list(TopicCluster.objects.all())
        self.assertEqual(clusters[0], cluster2)
        self.assertEqual(clusters[1], self.cluster)
