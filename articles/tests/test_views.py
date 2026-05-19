"""Tests for article API views — clusters, articles, tabs."""

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from articles.models import Tab, Source, Article, TopicCluster


@override_settings(
    REST_FRAMEWORK={
        'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
        'PAGE_SIZE': 20,
        'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
        'DEFAULT_THROTTLE_CLASSES': [],
    },
    CACHES={
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        },
    },
)
class ClusterViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.india_tab = Tab.objects.create(name="India", slug="india", order=1)
        self.sports_tab = Tab.objects.create(name="Sports", slug="sports", order=2)
        self.india_source = Source.objects.create(
            name="NDTV", url="https://ndtv.com/feed",
            category=self.india_tab, source_type="rss",
        )
        self.sports_source = Source.objects.create(
            name="ESPN", url="https://espn.com/feed",
            category=self.sports_tab, source_type="rss",
        )
        self.article1 = Article.objects.create(
            title="India News", url="https://ndtv.com/1",
            source=self.india_source, published_at=timezone.now(),
        )
        self.article2 = Article.objects.create(
            title="Sports News", url="https://espn.com/1",
            source=self.sports_source, published_at=timezone.now(),
        )
        self.cluster1 = TopicCluster.objects.create(
            topic_id="00000000-0000-0000-0000-000000000001",
            primary_article=self.article1, summary="India cluster.",
        )
        self.cluster2 = TopicCluster.objects.create(
            topic_id="00000000-0000-0000-0000-000000000002",
            primary_article=self.article2, summary="Sports cluster.",
        )

    def test_cluster_list(self):
        response = self.client.get("/api/clusters/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.data)
        self.assertIn("count", response.data)

    def test_cluster_list_tab_filter(self):
        response = self.client.get("/api/clusters/?tab=india")
        self.assertEqual(response.status_code, 200)
        results = response.data["results"]
        self.assertTrue(all(r["category_slug"] == "india" for r in results))

    def test_cluster_detail(self):
        response = self.client.get(f"/api/clusters/{self.cluster1.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["summary"], "India cluster.")

    def test_cluster_detail_not_found(self):
        response = self.client.get("/api/clusters/99999/")
        self.assertEqual(response.status_code, 404)

    def test_cluster_tabs_endpoint(self):
        response = self.client.get("/api/clusters/tabs/")
        self.assertEqual(response.status_code, 200)
        slugs = [t["slug"] for t in response.data]
        self.assertIn("india", slugs)
        self.assertIn("sports", slugs)

    def test_cluster_list_cached(self):
        response = self.client.get("/api/clusters/list_cached/")
        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.data, list)

    def test_cluster_list_cached_with_tab(self):
        response = self.client.get("/api/clusters/list_cached/?tab=india")
        self.assertEqual(response.status_code, 200)
        for item in response.data:
            self.assertEqual(item["category_slug"], "india")

    def test_cluster_list_pagination(self):
        for i in range(15):
            a = Article.objects.create(
                title=f"Article {i}", url=f"https://ndtv.com/{i}",
                source=self.india_source, published_at=timezone.now(),
            )
            TopicCluster.objects.create(
                topic_id=f"00000000-0000-0000-0000-{i:012d}",
                primary_article=a, summary=f"Cluster {i}",
            )
        response = self.client.get("/api/clusters/")
        self.assertIn("next", response.data)
        self.assertTrue(len(response.data["results"]) <= 20)

    def test_cluster_list_ordering(self):
        response = self.client.get("/api/clusters/?ordering=-created_at")
        self.assertEqual(response.status_code, 200)

    def test_cluster_related_excludes_self(self):
        extra = Article.objects.create(
            title="More India", url="https://ndtv.com/2",
            source=self.india_source, published_at=timezone.now(),
        )
        extra_cluster = TopicCluster.objects.create(
            topic_id="00000000-0000-0000-0000-000000000003",
            primary_article=extra, summary="Another india story.",
        )
        response = self.client.get(f"/api/clusters/{self.cluster1.pk}/related/")
        self.assertEqual(response.status_code, 200)
        ids = [item["id"] for item in response.data]
        self.assertNotIn(self.cluster1.pk, ids)
        self.assertIn(extra_cluster.pk, ids)
        for item in response.data:
            self.assertEqual(item["category_slug"], "india")


@override_settings(
    REST_FRAMEWORK={
        'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
        'PAGE_SIZE': 20,
        'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
        'DEFAULT_THROTTLE_CLASSES': [],
    },
    CACHES={
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        },
    },
)
class ArticleViewTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tab = Tab.objects.create(name="Global", slug="global", order=1)
        self.source = Source.objects.create(
            name="BBC", url="https://bbc.com/feed",
            category=self.tab, source_type="rss",
        )
        self.article = Article.objects.create(
            title="BBC Story", url="https://bbc.com/1",
            source=self.source, published_at=timezone.now(),
        )

    def test_article_list(self):
        response = self.client.get("/api/articles/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("results", response.data)

    def test_article_list_tab_filter(self):
        response = self.client.get("/api/articles/?tab=global")
        self.assertEqual(response.status_code, 200)
        for r in response.data["results"]:
            self.assertEqual(r["category_slug"], "global")

    def test_article_list_empty_tab(self):
        response = self.client.get("/api/articles/?tab=nonexistent")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data["results"]), 0)

    def test_article_detail(self):
        response = self.client.get(f"/api/articles/{self.article.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["title"], "BBC Story")

    def test_article_detail_not_found(self):
        response = self.client.get("/api/articles/99999/")
        self.assertEqual(response.status_code, 404)

    def test_article_list_unauthorized(self):
        response = self.client.get("/api/articles/")
        self.assertEqual(response.status_code, 200)
