<!-- BEGIN:nextjs-agent-rules -->
# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` before writing any code. Heed deprecation notices.
<!-- END:nextjs-agent-rules -->

<!-- BEGIN:backend-test-rules -->
# Backend Tests — NewsPulse

## Run Tests

```bash
cd news-pulse-backend

# Run all tests
python manage.py test --verbosity=2

# Run tests for a specific app
python manage.py test articles --verbosity=2
python manage.py test worker --verbosity=2
python manage.py test chat --verbosity=2
python manage.py test digest --verbosity=2
python manage.py test sources --verbosity=2
python manage.py test core --verbosity=2
python manage.py test users --verbosity=2

# Run a specific test class
python manage.py test articles.tests.test_views.ClusterViewTest --verbosity=2

# Run a specific test method
python manage.py test articles.tests.test_views.ClusterViewTest.test_cluster_list --verbosity=2

# Run with coverage (requires coverage.py)
coverage run --source='.' manage.py test --verbosity=2
coverage report
coverage html  # opens htmlcov/index.html
```

## Setup for Tests

The test suite uses PostgreSQL (same as production). Ensure a local PostgreSQL instance is running and accessible via the `DATABASE_*` env vars (defaults in `core/settings.py`).

Alternatively, set `USE_SQLITE_FOR_TESTS=true` in the env to use a local SQLite database for faster test runs.

Celery tasks run synchronously in tests via `CELERY_TASK_ALWAYS_EAGER=True` (set via `@override_settings` in each test).

OpenAI API calls are mocked via `unittest.mock.patch` — no real API key needed for tests.

## Test Conventions

- Use `django.test.TestCase` for tests needing a database.
- Use `django.test.SimpleTestCase` for pure unit tests (no DB needed).
- Use `rest_framework.test.APIClient` for API endpoint tests.
- Mock external services: OpenAI, `requests.get`, `send_mail`, cache backends.
- Use `@override_settings` for Celery eager mode, API keys, etc.
- Name test files `test_*.py` in `<app>/tests/` directories.
- Each `tests/` directory must have an `__init__.py`.

## Test File Inventory

| App | Test File | What It Covers |
|---|---|---|
| `articles` | `tests/test_models.py` | Tab, Source, Article, TopicCluster — creation, str, ordering, defaults |
| `articles` | `tests/test_serializers.py` | TabSerializer, ArticleSerializer, TopicClusterSerializer — fields, method fields, fallbacks |
| `articles` | `tests/test_views.py` | /api/clusters/ list, detail, tabs, cached, pagination, filtering /api/articles/ list, detail |
| `articles` | `tests/test_image_resolver.py` | URL validation, RSS/web image extraction, cluster image picking, resolution fallback, serializer |
| `worker` | `tests/test_article_content.py` | html_to_plain_text, extract_listing, enrich, rss content, prompts, fallback summary, gather articles, extract_keywords |
| `worker` | `tests/test_tasks.py` | Fetch page, cache invalidation, debounce, web/RSS extraction, tokenizer, TF-IDF, clustering, scrape_source, scrape_sources, cluster_and_summarize, summarize_clusters, embeddings, pipeline |
| `chat` | `tests/test_chat.py` | ChatMessage model, context builder, message list/send API, permissions, error handling |
| `digest` | `tests/test_digest.py` | EmailSubscriber model, top stories, digest HTML building, subscribe/unsubscribe/resend API, generate_daily_digest_task |
| `sources` | `tests/test_sources.py` | Source list (active only, excludes inactive), detail, read-only |
| `core` | `tests/test_health.py` | /health/ endpoint returns 200 with {"status": "ok"} |
| `core` | `tests/test_cache_utils.py` | CacheManager set/get/get_or_set/invalidate with JSON |
| `users` | `tests/test_auth.py` | Registration, login, me endpoint, token refresh, logout, token lifetimes, user models |
| `users` | `tests/test_personalization.py` | Decay function, interactions, affinity, personalized feed, session IDs, superuser |

## Writing New Tests

1. Create `tests/__init__.py` in the app directory if it doesn't exist.
2. Create `tests/test_<feature>.py` with test classes.
3. Follow existing patterns:
   - `setUp` creates reusable model instances via inline helper functions.
   - `APIClient()` for HTTP-level tests.
   - `from unittest.mock import patch, MagicMock` for mocking.
   - `@override_settings(CELERY_TASK_ALWAYS_EAGER=True)` for Celery tasks.
4. Test both success and failure paths.
5. Test edge cases (empty, None, malformed, boundaries).
<!-- END:backend-test-rules -->
