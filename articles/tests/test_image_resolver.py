"""Tests for article/cluster image resolution."""

from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings

from articles.image_resolver import (
    extract_rss_image,
    extract_web_image,
    pick_cluster_image,
    placeholder_url,
    resolve_cluster_display_image,
    validate_image_url,
)
from articles.models import Article, Source, Tab, TopicCluster


class ValidateImageUrlTests(SimpleTestCase):
    def test_accepts_https(self):
        url = "https://ichef.bbci.co.uk/ace/standard/240/test.jpg"
        self.assertEqual(validate_image_url(url), url)

    def test_rejects_http(self):
        self.assertIsNone(validate_image_url("http://example.com/a.jpg"))

    def test_rejects_data_uri(self):
        self.assertIsNone(validate_image_url("data:image/png;base64,abc"))


class ExtractRssImageTests(SimpleTestCase):
    def test_media_thumbnail(self):
        entry = SimpleNamespace(
            media_thumbnail=[{"url": "https://cdn.example.com/thumb.jpg"}],
            media_content=[],
            enclosures=[],
        )
        entry.get = lambda k, d="": d
        self.assertEqual(
            extract_rss_image(entry),
            "https://cdn.example.com/thumb.jpg",
        )

    def test_summary_img(self):
        entry = SimpleNamespace(
            media_thumbnail=[],
            media_content=[],
            enclosures=[],
            link="https://news.example.com/story",
        )
        entry.get = lambda k, d="": (
            '<p><img src="https://cdn.example.com/lead.jpg" /></p>'
            if k == "summary"
            else d
        )
        self.assertEqual(
            extract_rss_image(entry),
            "https://cdn.example.com/lead.jpg",
        )


class ExtractWebImageTests(SimpleTestCase):
    def test_finds_img_in_container(self):
        from bs4 import BeautifulSoup

        html = '<div class="card"><img src="/photos/1.jpg" /><h2>Title</h2></div>'
        container = BeautifulSoup(html, "html.parser").select_one("div")
        url = extract_web_image(container, "https://news.example.com/india/")
        self.assertEqual(url, "https://news.example.com/photos/1.jpg")


class PickClusterImageTests(TestCase):
    def setUp(self):
        self.tab = Tab.objects.create(name="India", slug="india", order=1)
        self.source = Source.objects.create(
            name="Test",
            url="https://example.com/feed",
            category=self.tab,
            source_type="rss",
        )

    @override_settings(BASE_URL="http://localhost:8000", PLACEHOLDER_BASE_URL="")
    def test_prefers_primary_then_sibling(self):
        primary = Article.objects.create(
            title="Primary",
            url="https://example.com/1",
            source=self.source,
            source_image_url="",
        )
        sibling = Article.objects.create(
            title="Sibling",
            url="https://example.com/2",
            source=self.source,
            source_image_url="https://cdn.example.com/sibling.jpg",
        )
        url = pick_cluster_image([primary, sibling], primary, "india")
        self.assertEqual(url, "https://cdn.example.com/sibling.jpg")

    @override_settings(BASE_URL="http://localhost:8000", PLACEHOLDER_BASE_URL="")
    def test_placeholder_when_no_images(self):
        primary = Article.objects.create(
            title="Primary",
            url="https://example.com/1",
            source=self.source,
        )
        url = pick_cluster_image([primary], primary, "india")
        self.assertEqual(
            url,
            "http://localhost:8000/static/newspulse/placeholders/india.jpg",
        )


class ResolveClusterDisplayImageTests(TestCase):
    def setUp(self):
        self.tab = Tab.objects.create(name="Global", slug="global", order=1)
        self.source = Source.objects.create(
            name="BBC",
            url="https://example.com/feed",
            category=self.tab,
            source_type="rss",
        )
        self.article = Article.objects.create(
            title="Story",
            url="https://example.com/story",
            source=self.source,
            source_image_url="https://cdn.example.com/article.jpg",
        )

    @override_settings(BASE_URL="http://localhost:8000", PLACEHOLDER_BASE_URL="")
    def test_fallback_chain(self):
        cluster = TopicCluster.objects.create(
            topic_id="00000000-0000-0000-0000-000000000001",
            primary_article=self.article,
            summary="Summary text",
            image_url="",
        )
        self.assertEqual(
            resolve_cluster_display_image(cluster),
            "https://cdn.example.com/article.jpg",
        )

        cluster.image_url = "https://cdn.example.com/cluster.jpg"
        cluster.save()
        self.assertEqual(
            resolve_cluster_display_image(cluster),
            "https://cdn.example.com/cluster.jpg",
        )


class TopicClusterSerializerImageTests(TestCase):
    def setUp(self):
        self.tab = Tab.objects.create(name="Sports", slug="sports", order=1)
        self.source = Source.objects.create(
            name="ESPN",
            url="https://example.com/feed",
            category=self.tab,
            source_type="rss",
        )
        self.article = Article.objects.create(
            title="Match",
            url="https://example.com/match",
            source=self.source,
            source_image_url="https://cdn.example.com/match.jpg",
        )
        self.cluster = TopicCluster.objects.create(
            topic_id="00000000-0000-0000-0000-000000000002",
            primary_article=self.article,
            summary="Game summary",
            image_url="https://cdn.example.com/cluster.jpg",
        )

    def test_serializer_includes_image_url(self):
        from articles.serializers import TopicClusterSerializer

        data = TopicClusterSerializer(self.cluster).data
        self.assertEqual(data["image_url"], "https://cdn.example.com/cluster.jpg")
