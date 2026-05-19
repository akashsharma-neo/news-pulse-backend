#!/bin/sh
# Run pending Django migrations, then exec the container command (e.g. gunicorn).
set -e

echo "==> Running database migrations..."
python manage.py migrate --noinput

exec "$@"
