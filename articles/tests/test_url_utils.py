"""Tests for article URL normalization."""

from django.test import SimpleTestCase

from articles.url_utils import normalize_article_url


class NormalizeArticleUrlTests(SimpleTestCase):
    def test_strips_www_and_trailing_slash(self):
        self.assertEqual(
            normalize_article_url("https://www.Example.com/path/"),
            "https://example.com/path",
        )

    def test_strips_utm_params(self):
        self.assertEqual(
            normalize_article_url(
                "https://example.com/story?utm_source=twitter&id=1"
            ),
            "https://example.com/story?id=1",
        )

    def test_strips_fragment(self):
        self.assertEqual(
            normalize_article_url("https://example.com/a#section"),
            "https://example.com/a",
        )
