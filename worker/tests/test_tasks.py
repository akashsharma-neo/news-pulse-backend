"""Tests for the NewsPulse Celery task pipeline — scraping, clustering, summarization, embeddings."""

import uuid
from datetime import timedelta
from unittest.mock import patch, MagicMock, ANY

import requests

from django.test import TestCase, override_settings
from django.utils import timezone

from articles.models import Tab, Source, Article, TopicCluster
from worker import tasks


class GetSourceTabSlugTest(TestCase):
    def test_known_source(self):
        self.assertEqual(tasks._get_source_tab_slug("BBC"), "global")

    def test_unknown_source(self):
        self.assertEqual(tasks._get_source_tab_slug("Nonexistent"), "global")


class FetchPageTest(TestCase):
    @patch("worker.tasks.requests.get")
    def test_successful_fetch(self, mock_get):
        mock_get.return_value.text = "<html>content</html>"
        mock_get.return_value.raise_for_status = lambda: None
        result = tasks._fetch_page("https://example.com", retries=1)
        self.assertEqual(result, "<html>content</html>")

    @patch("worker.tasks.requests.get")
    def test_retry_on_server_error(self, mock_get):
        def side_effect(*args, **kwargs):
            raise requests.HTTPError("500")
        mock_resp_fail = MagicMock(status_code=500)
        mock_resp_fail.raise_for_status.side_effect = side_effect
        mock_resp_ok = MagicMock(text="success")
        mock_resp_ok.raise_for_status = lambda: None
        mock_get.side_effect = [mock_resp_fail, mock_resp_ok]
        result = tasks._fetch_page("https://example.com", retries=2)
        self.assertEqual(result, "success")

    @patch("worker.tasks.requests.get")
    def test_client_error_returns_none(self, mock_get):
        mock_resp = MagicMock(status_code=404)
        mock_resp.raise_for_status.side_effect = requests.HTTPError("404")
        mock_get.return_value = mock_resp
        result = tasks._fetch_page("https://example.com", retries=1)
        self.assertIsNone(result)

    @patch("worker.tasks.requests.get")
    def test_all_retries_fail_returns_none(self, mock_get):
        mock_get.side_effect = requests.RequestException("Network error")
        result = tasks._fetch_page("https://example.com", retries=2)
        self.assertIsNone(result)


class InvalidateCacheTest(TestCase):
    @patch("django.core.cache.cache")
    def test_invalidate_cluster_feed_cache(self, mock_cache):
        mock_cache.delete_pattern = MagicMock()
        tasks.invalidate_cluster_feed_cache()
        mock_cache.delete_pattern.assert_called_once_with("clusters_list_v2_*")


class ScheduleClusterAfterScrapeTest(TestCase):
    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("django.core.cache.cache")
    def test_first_call_schedules(self, mock_cache):
        mock_cache.add.return_value = True
        result = tasks.schedule_cluster_after_scrape(countdown=10)
        self.assertTrue(result)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("django.core.cache.cache")
    def test_debounce_returns_false(self, mock_cache):
        mock_cache.add.return_value = False
        result = tasks.schedule_cluster_after_scrape(countdown=10)
        self.assertFalse(result)


class ExtractWebArticlesTest(TestCase):
    def test_extract_web_articles_from_html(self):
        html = """
        <div class="card">
            <h2><a href="/story1">First Story with enough detail</a></h2>
            <p>Content paragraph here.</p>
        </div>
        <div class="card">
            <h2><a href="https://example.com/story2">Second Story with enough detail</a></h2>
            <p>More content.</p>
        </div>
        """
        config = {
            "selector_title": "h2",
            "selector_content": "p",
        }
        articles = tasks._extract_web_articles(html, config, "https://example.com")
        self.assertEqual(len(articles), 2)
        self.assertEqual(articles[0]["title"], "First Story with enough detail")
        self.assertIn("Content paragraph", articles[0]["content"])

    def test_extract_web_articles_skips_short_titles(self):
        html = '<div class="card"><h2><a href="/x">Hi</a></h2></div>'
        config = {"selector_title": "h2", "selector_content": "p"}
        articles = tasks._extract_web_articles(html, config, "https://example.com")
        self.assertEqual(len(articles), 0)

    def test_extract_web_articles_resolves_relative_urls(self):
        html = '<div class="card"><h2><a href="/relative/path">Article Title here</a></h2></div>'
        config = {"selector_title": "h2", "selector_content": "p"}
        articles = tasks._extract_web_articles(html, config, "https://example.com/news/")
        self.assertIn("https://example.com", articles[0]["url"])

    def test_extract_web_articles_caps_at_50(self):
        cards = "".join(
            f'<div class="card"><h2><a href="/s{i}">Article {i} with enough detail</a></h2></div>'
            for i in range(60)
        )
        config = {"selector_title": "h2", "selector_content": "p"}
        articles = tasks._extract_web_articles(f"<body>{cards}</body>", config)
        self.assertLessEqual(len(articles), 50)

    def test_extract_web_articles_deduplicates_urls(self):
        html = """
        <div class="card"><h2><a href="/dup">First Story title here</a></h2></div>
        <div class="card"><h2><a href="/dup">Second Story title here</a></h2></div>
        """
        config = {"selector_title": "h2", "selector_content": "p"}
        articles = tasks._extract_web_articles(html, config, "https://example.com")
        self.assertEqual(len(articles), 1)


class ParseRssArticlesTest(TestCase):
    def test_parses_rss_entries(self):
        rss_xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0"><channel>
            <item>
                <title>RSS Story</title>
                <link>https://example.com/rss</link>
                <description>A test story about something important.</description>
            </item>
        </channel></rss>"""
        articles = tasks._parse_rss_articles(rss_xml, "BBC")
        self.assertEqual(len(articles), 1)
        self.assertEqual(articles[0]["title"], "RSS Story")

    @patch("feedparser.parse")
    def test_skips_entries_without_title(self, mock_parse):
        mock_entry = MagicMock()
        mock_entry.get.side_effect = lambda k, d="": {
            "title": "",
            "link": "https://example.com/rss",
        }.get(k, d)
        mock_parse.return_value.entries = [mock_entry]
        articles = tasks._parse_rss_articles("<rss>...</rss>", "BBC")
        self.assertEqual(len(articles), 0)

    @patch("feedparser.parse")
    def test_caps_at_50_entries(self, mock_parse):
        entries = []
        for i in range(60):
            e = MagicMock()
            e.get.side_effect = lambda k, d="", i=i: {
                "title": f"Story {i}",
                "link": f"https://example.com/{i}",
            }.get(k, d)
            entries.append(e)
        mock_parse.return_value.entries = entries
        articles = tasks._parse_rss_articles("<rss>...</rss>", "BBC")
        self.assertLessEqual(len(articles), 50)


class TokenizerAndSimilarityTest(TestCase):
    def test_tokenize(self):
        tokens = tasks._tokenize("Hello World! This is a test.")
        self.assertIn("hello", tokens)
        self.assertIn("world", tokens)
        self.assertIn("test", tokens)
        self.assertIn("this", tokens)

    def test_tfidf_vectorize(self):
        docs = ["apple banana apple", "banana banana"]
        vectors, vocab = tasks._tfidf_vectorize(docs)
        self.assertEqual(len(vocab), 2)
        self.assertEqual(len(vectors), 2)
        self.assertEqual(len(vectors[0]), 2)

    def test_cosine_similarity_identical(self):
        v = [1.0, 0.0]
        self.assertAlmostEqual(tasks._cosine_similarity(v, v), 1.0)

    def test_cosine_similarity_orthogonal(self):
        self.assertAlmostEqual(tasks._cosine_similarity([1.0, 0.0], [0.0, 1.0]), 0.0)

    def test_cosine_similarity_zero_vector(self):
        self.assertEqual(tasks._cosine_similarity([0.0, 0.0], [1.0, 0.0]), 0.0)

    def test_title_similarity_identical(self):
        self.assertAlmostEqual(tasks._title_similarity("Apple iPhone", "Apple iPhone"), 1.0)

    def test_title_similarity_no_overlap(self):
        self.assertEqual(tasks._title_similarity("Apple", "Banana"), 0.0)

    def test_title_similarity_empty(self):
        self.assertEqual(tasks._title_similarity("", "Apple"), 0.0)

    def test_content_similarity(self):
        tab = Tab.objects.create(name="T", slug="t", order=1)
        src = Source.objects.create(name="S", url="https://x.com", category=tab)
        a1 = Article.objects.create(title="Apple iPhone Launch", url="https://x.com/1", source=src,
                                     full_text="Apple launched new iPhone")
        a2 = Article.objects.create(title="Apple iPhone Event", url="https://x.com/2", source=src,
                                     full_text="Apple event for iPhone")
        sim = tasks._content_similarity(a1, a2)
        self.assertGreater(sim, 0.0)


class ClusterArticlesBySimilarityTest(TestCase):
    def setUp(self):
        self.tab = Tab.objects.create(name="T", slug="t", order=1)
        self.src = Source.objects.create(name="S", url="https://x.com", category=self.tab)

    def _make_article(self, title, text, dt=None):
        return Article.objects.create(
            title=title, url=f"https://x.com/{uuid.uuid4()}",
            source=self.src, full_text=text,
            published_at=dt or timezone.now(),
        )

    def test_clusters_similar_articles(self):
        a1 = self._make_article("Apple iPhone Launch Event", "Apple today announced the new iPhone with many features")
        a2 = self._make_article("iPhone Launch Apple Event", "Apple held an event for the new iPhone launch")
        clusters = tasks._cluster_articles_by_similarity([a1, a2], threshold=0.2)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(clusters[0]), 2)

    def test_separates_dissimilar_articles(self):
        a1 = self._make_article("Apple iPhone Launch", "Apple iPhone technology")
        a2 = self._make_article("Cricket World Cup 2024", "Cricket match scores results")
        clusters = tasks._cluster_articles_by_similarity([a1, a2], threshold=0.3)
        self.assertEqual(len(clusters), 2)

    def test_empty_list(self):
        self.assertEqual(tasks._cluster_articles_by_similarity([]), [])

    def test_single_article(self):
        a = self._make_article("Solo story", "Just one article here")
        clusters = tasks._cluster_articles_by_similarity([a])
        self.assertEqual(len(clusters), 1)
        self.assertEqual(len(clusters[0]), 1)


class ScrapeSourceTaskTest(TestCase):
    def setUp(self):
        self.tab = Tab.objects.create(name="T", slug="t", order=1)
        self.source = Source.objects.create(
            name="BBC", url="https://bbc.com/feed",
            category=self.tab, source_type="rss",
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("worker.tasks._fetch_page")
    @patch("worker.tasks._parse_rss_articles")
    @patch("worker.tasks.schedule_cluster_after_scrape")
    def test_scrape_source_creates_articles(self, mock_schedule, mock_parse, mock_fetch):
        mock_fetch.return_value = "<rss>...</rss>"
        mock_parse.return_value = [
            {"title": "Story 1", "url": "https://bbc.com/1", "content": "Body", "published_at": timezone.now()},
            {"title": "Story 2", "url": "https://bbc.com/2", "content": "Body", "published_at": timezone.now()},
        ]
        result = tasks.scrape_source(self.source.id)
        self.assertEqual(result["fetched"], 2)
        self.assertEqual(result["created"], 2)
        self.assertEqual(Article.objects.count(), 2)
        mock_schedule.assert_called_once()

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("worker.tasks._fetch_page")
    def test_scrape_source_handles_nonexistent(self, mock_fetch):
        result = tasks.scrape_source(99999)
        self.assertEqual(result["fetched"], 0)
        self.assertEqual(result["created"], 0)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("worker.tasks._fetch_page")
    @patch("worker.tasks.schedule_cluster_after_scrape")
    def test_scrape_source_deduplicates_urls(self, mock_schedule, mock_fetch):
        Article.objects.create(
            title="Existing", url="https://bbc.com/dup",
            source=self.source, published_at=timezone.now(),
        )
        mock_fetch.return_value = "<rss>...</rss>"
        import worker.tasks as wt
        with patch.object(wt, "_parse_rss_articles", return_value=[
            {"title": "Dup", "url": "https://bbc.com/dup", "content": "Body"},
        ]):
            result = tasks.scrape_source(self.source.id)
            self.assertEqual(result["skipped"], 1)


class ClusterAndSummarizeTaskTest(TestCase):
    def setUp(self):
        self.tab = Tab.objects.create(name="T", slug="t", order=1)
        self.src = Source.objects.create(
            name="S", url="https://x.com", category=self.tab,
        )
        self.article = Article.objects.create(
            title="Test Story", url="https://x.com/1",
            source=self.src, published_at=timezone.now(),
            full_text="Some article body text for clustering",
            fetched_at=timezone.now(),
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True, SUMMARIZE_ENABLED=False)
    @patch("worker.tasks.invalidate_cluster_feed_cache")
    @patch("worker.tasks.summarize_clusters.delay")
    def test_clusters_unclustered_skips_summarize_when_disabled(
        self, mock_summarize, mock_invalidate,
    ):
        result = tasks.cluster_and_summarize()
        self.assertEqual(result["clusters_created"], 1)
        mock_summarize.assert_not_called()
        mock_invalidate.assert_called_once()

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("worker.tasks.invalidate_cluster_feed_cache")
    @patch("worker.tasks.summarize_clusters.delay")
    def test_clusters_unclustered_articles(self, mock_summarize, mock_invalidate):
        result = tasks.cluster_and_summarize()
        self.assertEqual(result["clusters_created"], 1)
        self.assertEqual(result["articles_clustered"], 1)
        self.assertEqual(TopicCluster.objects.count(), 1)
        self.article.refresh_from_db()
        self.assertIsNotNone(self.article.topic_cluster_id)
        mock_summarize.assert_called_once()
        mock_invalidate.assert_called_once()

    def test_no_unclustered_articles(self):
        cluster = TopicCluster.objects.create(
            topic_id=uuid.uuid4(), primary_article=self.article, summary="",
        )
        self.article.topic_cluster = cluster
        self.article.save(update_fields=["topic_cluster"])
        result = tasks.cluster_and_summarize()
        self.assertEqual(result["clusters_created"], 0)


class SummarizeClustersTaskTest(TestCase):
    def setUp(self):
        self.tab = Tab.objects.create(name="T", slug="t", order=1)
        self.src = Source.objects.create(
            name="BBC", url="https://bbc.com/feed", category=self.tab,
        )
        body = (
            "The government announced new policy measures today affecting transport and trade. "
            "Officials said the changes would take effect immediately across major cities. "
            "Opposition leaders criticized the timing while industry groups welcomed clarity. "
            "Analysts noted the move could reshape regional supply chains over the coming months."
        )
        self.article = Article.objects.create(
            title="Test", url="https://bbc.com/1", source=self.src,
            published_at=timezone.now(),
            full_text=body,
        )
        self.cluster = TopicCluster.objects.create(
            topic_id=uuid.uuid4(), primary_article=self.article,
            summary="", sources=["BBC"],
        )
        self.article.topic_cluster = self.cluster
        self.article.save(update_fields=["topic_cluster"])

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_single_source_uses_fallback(self):
        result = tasks.summarize_clusters()
        self.assertEqual(result["summarized"], 1)
        self.cluster.refresh_from_db()
        self.assertTrue(len(self.cluster.summary) > 0)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True, OPENAI_COMPATIBLE_API_KEY="sk-test")
    @patch("openai.OpenAI")
    def test_multi_source_calls_openai(self, mock_openai):
        cnn_src = Source.objects.create(
            name="CNN", url="https://cnn.com/feed", category=self.tab,
        )
        cnn_article = Article.objects.create(
            title="Test story continues",
            url="https://cnn.com/1",
            source=cnn_src,
            published_at=timezone.now(),
            full_text=(
                "Officials confirmed the same policy details in a briefing that outlined "
                "economic impacts and regional implementation timelines for the new rules."
            ),
            topic_cluster=self.cluster,
        )
        self.cluster.sources = ["BBC", "CNN"]
        self.cluster.save()
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content=" ".join(["newsword"] * 95)))],
        )
        result = tasks.summarize_clusters()
        self.assertEqual(result["summarized"], 1)
        self.cluster.refresh_from_db()
        self.assertGreaterEqual(len(self.cluster.summary.split()), 85)
        del cnn_article

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True, SUMMARIZE_ENABLED=False)
    def test_summarize_disabled(self):
        result = tasks.summarize_clusters()
        self.assertTrue(result.get("disabled"))
        self.assertEqual(result["summarized"], 0)
        self.cluster.refresh_from_db()
        self.assertEqual(self.cluster.summary, "")

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_no_clusters_to_summarize(self):
        self.cluster.summary = "Already summarized"
        self.cluster.save()
        result = tasks.summarize_clusters()
        self.assertEqual(result["summarized"], 0)


class EmbeddingTasksTest(TestCase):
    @override_settings(CELERY_TASK_ALWAYS_EAGER=True, EMBEDDINGS_ENABLED=False)
    def test_embeddings_disabled(self):
        result = tasks.generate_embeddings_task()
        self.assertTrue(result.get("disabled"))

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True, EMBEDDINGS_ENABLED=False)
    def test_cluster_embeddings_disabled(self):
        result = tasks.generate_cluster_embeddings_task()
        self.assertTrue(result.get("disabled"))


class RunFullPipelineTest(TestCase):
    @override_settings(CELERY_TASK_ALWAYS_EAGER=True, EMBEDDINGS_ENABLED=False)
    @patch("worker.tasks.scrape_sources.delay")
    def test_pipeline_dispatches_scrape(self, mock_scrape):
        mock_scrape.return_value.id = "mock-id"
        result = tasks.run_full_pipeline()
        self.assertIn("scrape_chord_id", result)
        mock_scrape.assert_called_once()

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True, EMBEDDINGS_ENABLED=True)
    @patch("worker.tasks.scrape_sources.delay")
    @patch("worker.tasks.generate_embeddings_task.delay")
    @patch("worker.tasks.generate_cluster_embeddings_task.delay")
    def test_pipeline_with_embeddings(self, mock_ce, mock_ge, mock_scrape):
        mock_scrape.return_value.id = "scrape-id"
        mock_ge.return_value.id = "embed-id"
        mock_ce.return_value.id = "ce-id"
        result = tasks.run_full_pipeline()
        self.assertIn("embed_task_id", result)
        self.assertIn("cluster_embed_task_id", result)
