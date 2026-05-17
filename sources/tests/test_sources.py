"""Tests for the sources API — listing active/excluding inactive sources."""

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from django.contrib.auth import get_user_model

from articles.models import Tab, Source


@override_settings(REST_FRAMEWORK={
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
})
class SourceAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.tab = Tab.objects.create(name="India", slug="india", order=1)
        self.active_source = Source.objects.create(
            name="NDTV", url="https://ndtv.com/feed",
            category=self.tab, source_type="rss", active=True,
        )
        self.inactive_source = Source.objects.create(
            name="Inactive", url="https://old.com/feed",
            category=self.tab, source_type="rss", active=False,
        )

    def test_source_list_returns_active(self):
        response = self.client.get("/api/sources/")
        self.assertEqual(response.status_code, 200)
        names = [s["name"] for s in response.data["results"]]
        self.assertIn("NDTV", names)
        self.assertNotIn("Inactive", names)

    def test_source_detail(self):
        response = self.client.get(f"/api/sources/{self.active_source.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["name"], "NDTV")

    def test_source_detail_not_found(self):
        response = self.client.get("/api/sources/99999/")
        self.assertEqual(response.status_code, 404)

    def test_source_read_only(self):
        User = get_user_model()
        user = User.objects.create_user(email="test@example.com", password="test123")
        self.client.force_authenticate(user=user)
        response = self.client.post("/api/sources/", {"name": "New"}, format="json")
        self.assertEqual(response.status_code, 405)

    def test_source_list_serializer_fields(self):
        response = self.client.get(f"/api/sources/{self.active_source.pk}/")
        for field in ["id", "name", "url", "category", "source_type", "active"]:
            self.assertIn(field, response.data)

    def test_source_list_pagination(self):
        response = self.client.get("/api/sources/")
        self.assertIn("results", response.data)
        self.assertIn("count", response.data)
