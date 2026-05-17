"""Test settings — uses SQLite so tests run without PostgreSQL."""
import os
from .settings import *  # noqa: F401, F403

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}

# Use local memory cache instead of Redis
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}

# Disable migrations that require pgvector
MIGRATION_MODULES = {}
for app_label in ['articles', 'users', 'chat', 'digest', 'sources', 'core', 'worker']:
    MIGRATION_MODULES[app_label] = None

# Run Celery tasks synchronously
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Disable embeddings
EMBEDDINGS_ENABLED = False

# Mock OpenAI
OPENAI_COMPATIBLE_API_KEY = 'sk-test-key'
OPENAI_COMPATIBLE_BASE_URL = 'https://test.api.com/v1'
OPENAI_COMPATIBLE_MODEL = 'gpt-4o-mini'
SUMMARIZE_FETCH_FULL_BODY = False

# Email
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'
DEFAULT_FROM_EMAIL = 'test@newspulse.app'
BASE_URL = 'http://localhost:8000'

# Disable SSL redirect, etc.
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
