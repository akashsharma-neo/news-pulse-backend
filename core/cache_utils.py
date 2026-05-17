"""
Utility for interacting with the Redis cache layer.
Provides high-level abstractions for common NewsPulse caching patterns.
"""

from django.core.cache import cache
import json

class CacheManager:
    """
    Handles structured caching for NewsPulse entities (feeds, clusters, etc.).
    """

    @staticmethod
    def set_json(key: str, value: dict, timeout: int = 3600):
        """Sets a JSON-serializable dictionary in the cache."""
        cache.set(key, json.dumps(value), timeout=timeout)

    @staticmethod
    def get_json(key: str) -> dict | None:
        """Retrieves and deserializes a JSON dictionary from the cache."""
        data = cache.get(key)
        if data is None:
            return None
        try:
            return json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return None

    @staticmethod
    def get_or_set(key: str, fetcher_func, timeout: int = 3600):
        """
        The primary pattern for API caching.
        Checks cache; if miss, executes fetcher_func, caches result, and returns it.
        """
        cached_data = CacheManager.get_json(key)
        if cached_data is not None:
            return cached_data

        # Cache Miss
        new_data = fetcher_func()
        if new_data is not None:
            CacheManager.set_json(key, new_data, timeout=timeout)
        
        return new_data

    @staticmethod
    def invalidate(key: str):
        """Deletes a specific cache key."""
        cache.delete(key)
