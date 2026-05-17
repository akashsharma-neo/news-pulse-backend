"""Tests for the health check endpoint."""

from django.test import SimpleTestCase
from django.urls import reverse


class HealthTest(SimpleTestCase):
    def test_health_returns_ok(self):
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_health_no_auth_required(self):
        response = self.client.get("/health/")
        self.assertEqual(response.status_code, 200)
