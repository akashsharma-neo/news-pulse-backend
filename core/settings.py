"""NewsPulse Django settings — configuration for database, REST framework, Celery, and third-party services."""
import os
from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from core.env_config import apply_profile

BASE_DIR = Path(__file__).resolve().parent.parent

NEWSMINE_ENV = apply_profile()
IS_PROD = NEWSMINE_ENV == 'prod'
IS_STAGING = NEWSMINE_ENV == 'staging'
IS_DEPLOYED = IS_PROD or IS_STAGING
ENABLE_API_DOCS = NEWSMINE_ENV == 'dev'

SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'django-insecure-change-me-in-production')

DEBUG = os.environ.get('DJANGO_DEBUG', 'True').lower() in ('true', '1', 'yes')
if IS_DEPLOYED:
    DEBUG = False

_allowed = os.environ.get('DJANGO_ALLOWED_HOSTS', '*').strip()
ALLOWED_HOSTS = ['*'] if _allowed == '*' else [h.strip() for h in _allowed.split(',') if h.strip()]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third party
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'drf_spectacular',
    'corsheaders',
    # Local apps
    'core',
    'articles',
    'sources',
    'worker',
    'chat',
    'digest',
    'users',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'core.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'core.wsgi.application'

# Database — PostgreSQL by default (SQLite fallback if not available)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ.get('DATABASE_NAME', 'newspulse'),
        'USER': os.environ.get('DATABASE_USER', 'akashsharma'),
        'PASSWORD': os.environ.get('DATABASE_PASSWORD', ''),
        'HOST': os.environ.get('DATABASE_HOST', 'localhost'),
        'PORT': os.environ.get('DATABASE_PORT', '5432'),
    }
}

AUTH_USER_MODEL = 'users.User'

AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Kolkata'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Placeholder images for stories without a publisher lead image (dev: staticfiles; prod: S3 prefix)
PLACEHOLDER_BASE_URL = os.environ.get('PLACEHOLDER_BASE_URL', '').strip()

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': (
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ),
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_THROTTLE_CLASSES': (
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
        'rest_framework.throttling.ScopedRateThrottle',
    ),
    'DEFAULT_THROTTLE_RATES': {
        'anon': '120/hour',
        'user': '2000/hour',
        'auth': '30/hour',
        'chat_send': '60/hour',
        'digest_subscribe': '10/hour',
    },
}

# JWT Settings
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=7),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=30),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': 'Bearer',
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
}

# Celery
CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_ACCEPT_CONTENT = ['json']
# Richer task timeline/history in Flower (and other monitors using Celery events).
CELERY_WORKER_SEND_TASK_EVENTS = True
CELERY_TASK_SEND_SENT_EVENT = True
CELERY_TASK_ROUTES = {
    'worker.tasks.generate_embeddings_task': {'queue': 'embeddings'},
    'worker.tasks.generate_cluster_embeddings_task': {'queue': 'embeddings'},
}

# Redis (caching)
CACHES = {
    'default': {
        'BACKEND': 'django_redis.cache.RedisCache',
        'LOCATION': os.environ.get('REDIS_URL', 'redis://localhost:6379/1'),
        'OPTIONS': {
            'CLIENT_CLASS': 'django_redis.client.DefaultClient',
        }
    }
}

# OpenAI-compatible LLM API (OpenRouter, OpenAI, etc.)
# Prefer OPENAI_COMPATIBLE_*; OPENAI_* names are legacy fallbacks.
OPENAI_COMPATIBLE_API_KEY = os.environ.get(
    'OPENAI_COMPATIBLE_API_KEY',
    os.environ.get('OPENAI_API_KEY', ''),
)
OPENAI_COMPATIBLE_BASE_URL = os.environ.get(
    'OPENAI_COMPATIBLE_BASE_URL',
    os.environ.get('OPENAI_BASE_URL', 'https://openrouter.ai/api/v1'),
)
OPENAI_COMPATIBLE_MODEL = os.environ.get(
    'OPENAI_COMPATIBLE_MODEL',
    os.environ.get('OPENAI_MODEL', ''),
)

# Article chat — OpenRouter web search (openrouter:web_search server tool)
_chat_web_search_env = os.environ.get('CHAT_WEB_SEARCH_ENABLED', '').lower()
if _chat_web_search_env in ('true', '1', 'yes'):
    CHAT_WEB_SEARCH_ENABLED = True
elif _chat_web_search_env in ('false', '0', 'no'):
    CHAT_WEB_SEARCH_ENABLED = False
else:
    CHAT_WEB_SEARCH_ENABLED = 'openrouter.ai' in OPENAI_COMPATIBLE_BASE_URL
CHAT_WEB_SEARCH_MAX_RESULTS = int(os.environ.get('CHAT_WEB_SEARCH_MAX_RESULTS', '5'))
CHAT_WEB_SEARCH_MAX_TOTAL_RESULTS = int(
    os.environ.get('CHAT_WEB_SEARCH_MAX_TOTAL_RESULTS', '10')
)
CHAT_MAX_TOKENS = int(os.environ.get('CHAT_MAX_TOKENS', '1024'))
CHAT_TEMPERATURE = float(os.environ.get('CHAT_TEMPERATURE', '0.7'))

SUMMARIZE_BATCH_SIZE = int(os.environ.get('SUMMARIZE_BATCH_SIZE', '12'))
SUMMARIZE_DELAY_SEC = float(os.environ.get('SUMMARIZE_DELAY_SEC', '4'))
SUMMARIZE_MAX_TOKENS = int(os.environ.get('SUMMARIZE_MAX_TOKENS', '250'))
SUMMARIZE_FETCH_FULL_BODY = os.environ.get(
    'SUMMARIZE_FETCH_FULL_BODY', 'false'
).lower() in ('true', '1', 'yes')
SUMMARIZE_ENABLED = os.environ.get('SUMMARIZE_ENABLED', 'true').lower() in (
    'true', '1', 'yes'
)

EMBEDDINGS_ENABLED = os.environ.get('EMBEDDINGS_ENABLED', 'false').lower() in (
    'true', '1', 'yes'
)

# Legacy aliases (deprecated env names)
OPENAI_API_KEY = OPENAI_COMPATIBLE_API_KEY
OPENAI_BASE_URL = OPENAI_COMPATIBLE_BASE_URL
OPENAI_MODEL = OPENAI_COMPATIBLE_MODEL

# ---------------------------------------------------------------------------
# Swagger / OpenAPI (drf-spectacular)
# ---------------------------------------------------------------------------
SPECTACULAR_SETTINGS = {
    'TITLE': 'NewsPulse API',
    'DESCRIPTION': 'Conversational news aggregator — scrape, cluster, summarize, chat.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'SCHEMA_PATH_PREFIX': '/api/',
    'SCHEMA_PATH_PREFIX_TRIM': True,
    'POSTPROCESSING_HOOKS': [
        'drf_spectacular.hooks.postprocess_schema_enums',
    ],
}

# ---------------------------------------------------------------------------
# Scraper settings
# ---------------------------------------------------------------------------
SCRAPER_USER_AGENT = 'NewsPulse/1.0 (News Aggregator; +https://newspulse.app; contact@newspulse.app)'
SCRAPER_DELAY = 1.0  # seconds between requests to same domain

# CORS — comma-separated origins in CORS_ALLOWED_ORIGINS
_cors_raw = os.environ.get(
    'CORS_ALLOWED_ORIGINS',
    'http://localhost:3000,http://127.0.0.1:3000',
)
CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors_raw.split(',') if o.strip()]

# ---------------------------------------------------------------------------
# Email (SMTP)
# ---------------------------------------------------------------------------
EMAIL_BACKEND = os.environ.get(
    'EMAIL_BACKEND',
    'django.core.mail.backends.smtp.EmailBackend',
)
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'localhost')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', 587))
EMAIL_USE_TLS = os.environ.get('EMAIL_USE_TLS', 'True').lower() in ('true', '1', 'yes')
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.environ.get('DEFAULT_FROM_EMAIL', 'news@newspulse.app')

# Base URL for unsubscribe links (set in dev .env)
BASE_URL = os.environ.get('BASE_URL', 'http://localhost:8000')

# ---------------------------------------------------------------------------
# Celery Beat — periodic tasks
# ---------------------------------------------------------------------------
CELERY_BEAT_SCHEDULE = {
    'scrape-every-30-minutes': {
        'task': 'worker.tasks.scrape_sources',
        'schedule': 1800,  # 30 minutes
    },
    'cluster-every-hour': {
        'task': 'worker.tasks.cluster_and_summarize',
        'schedule': 3600,  # 1 hour safety net for unclustered articles
    },
    'daily-digest': {
        'task': 'digest.tasks.generate_daily_digest_task',
        'schedule': 86400,  # every 24 hours
    },
}

if SUMMARIZE_ENABLED:
    CELERY_BEAT_SCHEDULE['summarize-clusters'] = {
        'task': 'worker.tasks.summarize_clusters',
        'schedule': 3600,  # every hour as backup
    }

if EMBEDDINGS_ENABLED:
    CELERY_BEAT_SCHEDULE['embed-every-2-hours'] = {
        'task': 'worker.tasks.generate_embeddings_task',
        'schedule': 7200,
    }
    CELERY_BEAT_SCHEDULE['embed-clusters-every-2-hours'] = {
        'task': 'worker.tasks.generate_cluster_embeddings_task',
        'schedule': 7200,
    }

# ---------------------------------------------------------------------------
# Production / staging security (HTTPS behind reverse proxy)
# ---------------------------------------------------------------------------
if IS_DEPLOYED:
    SECURE_SSL_REDIRECT = os.environ.get('SECURE_SSL_REDIRECT', 'true').lower() in ('true', '1', 'yes')
    SECURE_REDIRECT_EXEMPT = [r'^health/$']
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', '31536000'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = os.environ.get('SECURE_HSTS_PRELOAD', 'false').lower() in ('true', '1', 'yes')
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_CONTENT_TYPE_NOSNIFF = True
    SECURE_BROWSER_XSS_FILTER = True
    X_FRAME_OPTIONS = 'DENY'


def _validate_deployed_settings() -> None:
    """Fail fast when prod/staging is misconfigured."""
    if not IS_DEPLOYED:
        return

    insecure_markers = ('django-insecure', 'dev-insecure', 'change-me')
    if not SECRET_KEY or len(SECRET_KEY) < 50 or any(m in SECRET_KEY.lower() for m in insecure_markers):
        raise ImproperlyConfigured(
            'Set DJANGO_SECRET_KEY to a unique random string of at least 50 characters for prod/staging.'
        )

    if not ALLOWED_HOSTS or '*' in ALLOWED_HOSTS:
        raise ImproperlyConfigured(
            'Set DJANGO_ALLOWED_HOSTS to your API domain(s) only (no * wildcard) for prod/staging.'
        )
    if any(h in ('0.0.0.0', '') for h in ALLOWED_HOSTS):
        raise ImproperlyConfigured(
            'DJANGO_ALLOWED_HOSTS must not include 0.0.0.0 for prod/staging.'
        )

    if not CORS_ALLOWED_ORIGINS:
        raise ImproperlyConfigured(
            'Set CORS_ALLOWED_ORIGINS to your frontend origin(s) for prod/staging.'
        )
    if IS_PROD:
        for origin in CORS_ALLOWED_ORIGINS:
            if not origin.startswith('https://'):
                raise ImproperlyConfigured(
                    f'Production CORS origin must use HTTPS: {origin!r}'
                )


_validate_deployed_settings()
