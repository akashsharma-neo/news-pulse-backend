"""Tests for CacheManager utility — set/get/invalidate with JSON serialization."""

from unittest.mock import patch

from django.test import SimpleTestCase
from core.cache_utils import CacheManager


class CacheManagerTest(SimpleTestCase):
    @patch("core.cache_utils.cache")
    def test_set_json(self, mock_cache):
        CacheManager.set_json("key", {"foo": "bar"}, timeout=600)
        mock_cache.set.assert_called_once_with("key", '{"foo": "bar"}', timeout=600)

    @patch("core.cache_utils.cache")
    def test_get_json_hit(self, mock_cache):
        mock_cache.get.return_value = '{"foo": "bar"}'
        result = CacheManager.get_json("key")
        self.assertEqual(result, {"foo": "bar"})

    @patch("core.cache_utils.cache")
    def test_get_json_miss(self, mock_cache):
        mock_cache.get.return_value = None
        result = CacheManager.get_json("key")
        self.assertIsNone(result)

    @patch("core.cache_utils.cache")
    def test_get_json_decode_error(self, mock_cache):
        mock_cache.get.return_value = "not json"
        result = CacheManager.get_json("key")
        self.assertIsNone(result)

    @patch("core.cache_utils.cache")
    def test_get_or_set_cache_hit(self, mock_cache):
        mock_cache.get.return_value = '{"cached": true}'
        fetcher = lambda: {"fresh": True}
        result = CacheManager.get_or_set("key", fetcher, timeout=300)
        self.assertEqual(result, {"cached": True})

    @patch("core.cache_utils.cache")
    def test_get_or_set_cache_miss(self, mock_cache):
        mock_cache.get.return_value = None
        fetcher = lambda: {"fresh": True}
        result = CacheManager.get_or_set("key", fetcher, timeout=300)
        self.assertEqual(result, {"fresh": True})
        mock_cache.set.assert_called_once()

    @patch("core.cache_utils.cache")
    def test_get_or_set_fetcher_returns_none(self, mock_cache):
        mock_cache.get.return_value = None
        fetcher = lambda: None
        result = CacheManager.get_or_set("key", fetcher, timeout=300)
        self.assertIsNone(result)
        mock_cache.set.assert_not_called()

    @patch("core.cache_utils.cache")
    def test_invalidate(self, mock_cache):
        CacheManager.invalidate("my_key")
        mock_cache.delete.assert_called_once_with("my_key")
