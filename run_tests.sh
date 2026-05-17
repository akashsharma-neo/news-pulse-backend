#!/bin/bash
# Run NewsPulse backend tests with local infrastructure.
# Uses local PostgreSQL and in-memory Redis mock.

export DATABASE_HOST=localhost
export DATABASE_USER=akashsharma
export DATABASE_PASSWORD=''
export DATABASE_NAME=newspulse
export DATABASE_PORT=5432

# Use local Redis or locmem cache
export REDIS_URL=redis://localhost:6379/1
export CELERY_BROKER_URL=redis://localhost:6379/0
export CELERY_RESULT_BACKEND=redis://localhost:6379/0

export DJANGO_SECRET_KEY='test-secret-key-50-chars-minimum-required-for-prod-check-xxx'
export NEWSMINE_ENV=test
export CELERY_TASK_ALWAYS_EAGER=True
export CELERY_TASK_EAGER_PROPAGATES=True
export DJANGO_DEBUG=true
export EMBEDDINGS_ENABLED=false
export SUMMARIZE_FETCH_FULL_BODY=false
export EMAIL_BACKEND=django.core.mail.backends.locmem.EmailBackend

APPS="${1:-articles worker chat digest sources core users}"

VENV_PYTHON="$(dirname "$0")/venv/bin/python"
MANAGE="$(dirname "$0")/manage.py"

exec "$VENV_PYTHON" "$MANAGE" test $APPS --verbosity=2
