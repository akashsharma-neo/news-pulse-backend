"""Tests for the digest app — subscription, unsubscribe, resend, and the Celery task."""

from unittest.mock import patch, MagicMock

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

_THROTTLE_OVERRIDE = {
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
        'rest_framework.throttling.ScopedRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': '1000000/hour',
        'user': '1000000/hour',
        'auth': '1000000/hour',
        'chat_send': '1000000/hour',
        'digest_subscribe': '1000000/hour',
    },
}

from articles.models import Tab, Source, Article, TopicCluster
from digest.models import EmailSubscriber
from digest.tasks import _get_top_stories, _build_digest_html, generate_daily_digest_task


class EmailSubscriberModelTest(TestCase):
    def setUp(self):
        self.sub = EmailSubscriber.objects.create(
            email="test@example.com", tabs=["india", "sports"],
        )

    def test_subscriber_creation(self):
        self.assertEqual(self.sub.email, "test@example.com")
        self.assertTrue(self.sub.is_active)
        self.assertEqual(self.sub.tabs, ["india", "sports"])
        self.assertIsNotNone(self.sub.unsubscribe_token)

    def test_subscriber_str(self):
        self.assertEqual(str(self.sub), "test@example.com")

    def test_subscriber_unique_token(self):
        sub2 = EmailSubscriber.objects.create(email="other@example.com")
        self.assertNotEqual(self.sub.unsubscribe_token, sub2.unsubscribe_token)

    def test_subscriber_unique_email(self):
        with self.assertRaises(Exception):
            EmailSubscriber.objects.create(email="test@example.com")


class GetTopStoriesTest(TestCase):
    def setUp(self):
        self.tab = Tab.objects.create(name="India", slug="india", order=1)
        self.src = Source.objects.create(
            name="NDTV", url="https://ndtv.com", category=self.tab,
        )
        self.article = Article.objects.create(
            title="Top Story", url="https://ndtv.com/1",
            source=self.src, published_at=timezone.now(),
        )
        self.cluster = TopicCluster.objects.create(
            topic_id="00000000-0000-0000-0000-000000000001",
            primary_article=self.article, summary="Test summary.",
        )

    def test_returns_recent_stories(self):
        stories = _get_top_stories(limit=10)
        self.assertEqual(len(stories), 1)

    def test_filters_by_tabs(self):
        stories = _get_top_stories(tabs=["sports"], limit=10)
        self.assertEqual(len(stories), 0)

    def test_respects_limit(self):
        for i in range(5):
            a = Article.objects.create(
                title=f"Story {i}", url=f"https://ndtv.com/{i}",
                source=self.src, published_at=timezone.now(),
            )
            TopicCluster.objects.create(
                topic_id=f"00000000-0000-0000-0000-{i:012d}",
                primary_article=a, summary="Summary.",
            )
        stories = _get_top_stories(limit=3)
        self.assertEqual(len(stories), 3)


class BuildDigestHtmlTest(TestCase):
    def setUp(self):
        self.tab = Tab.objects.create(name="T", slug="t", order=1)
        self.src = Source.objects.create(
            name="S", url="https://x.com", category=self.tab,
        )
        self.article = Article.objects.create(
            title="Test Article", url="https://x.com/1",
            source=self.src, published_at=timezone.now(),
        )
        self.cluster = TopicCluster.objects.create(
            topic_id="00000000-0000-0000-0000-000000000001",
            primary_article=self.article, summary="A short summary.",
            sources=["BBC", "CNN"],
        )

    def test_build_digest_html_returns_subject_body_html(self):
        subject, body_text, body_html = _build_digest_html([self.cluster], tabs=["india"])
        self.assertIn("Daily Digest", subject)
        self.assertIn("Test Article", body_html)
        self.assertIn("BBC, CNN", body_html)
        self.assertIn("Test Article", body_text)

    def test_build_digest_html_no_tabs(self):
        subject, body_text, body_html = _build_digest_html([self.cluster])
        self.assertIn("all topics", subject)


@override_settings(REST_FRAMEWORK=_THROTTLE_OVERRIDE)
class SubscribeAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/digest/subscribe/"

    def test_subscribe_valid(self):
        response = self.client.post(self.url, {"email": "user@example.com", "tabs": ["india"]}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(EmailSubscriber.objects.filter(email="user@example.com").exists())

    def test_subscribe_invalid_email(self):
        response = self.client.post(self.url, {"email": "not-an-email"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_subscribe_reactivates(self):
        sub = EmailSubscriber.objects.create(email="existing@example.com", is_active=False)
        response = self.client.post(self.url, {"email": "existing@example.com"}, format="json")
        self.assertEqual(response.status_code, 200)
        sub.refresh_from_db()
        self.assertTrue(sub.is_active)


@override_settings(REST_FRAMEWORK=_THROTTLE_OVERRIDE)
class UnsubscribeAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.sub = EmailSubscriber.objects.create(email="sub@example.com")

    def test_unsubscribe_valid_token(self):
        response = self.client.get(f"/api/digest/unsubscribe/?token={self.sub.unsubscribe_token}")
        self.assertEqual(response.status_code, 200)
        self.sub.refresh_from_db()
        self.assertFalse(self.sub.is_active)

    def test_unsubscribe_invalid_token(self):
        response = self.client.get("/api/digest/unsubscribe/?token=00000000-0000-0000-0000-000000000000")
        self.assertEqual(response.status_code, 404)

    def test_unsubscribe_missing_token(self):
        response = self.client.get("/api/digest/unsubscribe/")
        self.assertEqual(response.status_code, 400)


@override_settings(REST_FRAMEWORK=_THROTTLE_OVERRIDE)
class ResendDigestAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/api/digest/resend/"
        from django.contrib.auth import get_user_model
        User = get_user_model()
        self.admin = User.objects.create_superuser(
            email="admin@example.com", password="admin123",
        )
        self.user = User.objects.create_user(
            email="user@example.com", password="user123",
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("digest.tasks.send_mail")
    def test_resend_admin_only(self, mock_mail):
        self.client.force_authenticate(user=self.user)
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 403)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("digest.tasks.send_mail")
    def test_resend_admin_success(self, mock_mail):
        self.client.force_authenticate(user=self.admin)
        EmailSubscriber.objects.create(email="sub@example.com", tabs=["india"])
        response = self.client.post(self.url)
        self.assertEqual(response.status_code, 202)
        self.assertIn("task_id", response.data)


class GenerateDailyDigestTaskTest(TestCase):
    def setUp(self):
        self.tab = Tab.objects.create(name="India", slug="india", order=1)
        self.src = Source.objects.create(
            name="NDTV", url="https://ndtv.com", category=self.tab,
        )
        self.article = Article.objects.create(
            title="Digest Story", url="https://ndtv.com/1",
            source=self.src, published_at=timezone.now(),
        )
        self.cluster = TopicCluster.objects.create(
            topic_id="00000000-0000-0000-0000-000000000001",
            primary_article=self.article, summary="Digest summary.",
            sources=["NDTV"],
        )
        self.sub = EmailSubscriber.objects.create(
            email="digest@example.com", tabs=["india"],
        )

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("digest.tasks.send_mail")
    def test_sends_digest_to_active_subscribers(self, mock_mail):
        result = generate_daily_digest_task()
        self.assertEqual(result["sent"], 1)
        self.assertEqual(result["failed"], 0)
        self.assertEqual(result["total_subscribers"], 1)
        mock_mail.assert_called_once()

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("digest.tasks.send_mail")
    def test_skips_inactive_subscribers(self, mock_mail):
        self.sub.is_active = False
        self.sub.save()
        result = generate_daily_digest_task()
        self.assertEqual(result["total_subscribers"], 0)
        self.assertEqual(result["sent"], 0)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    @patch("digest.tasks.send_mail")
    def test_no_subscribers(self, mock_mail):
        EmailSubscriber.objects.all().delete()
        result = generate_daily_digest_task()
        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["total_subscribers"], 0)
