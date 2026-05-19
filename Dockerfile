# syntax=docker/dockerfile:1
# ===========================
# NewsPulse — Multi-stage Dockerfile
# ===========================
# Targets:
#   runtime     — Django + Celery (prod default; no PyTorch/CUDA)
#   embeddings  — runtime + sentence-transformers (optional profile only)
#
# Prod CI builds `runtime` only. See requirements-embeddings.txt and
# docs/docker-images.md.

FROM python:3.14-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


FROM python:3.14-slim AS runtime

RUN groupadd -r app && useradd -r -g app -d /app -s /sbin/nologin app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local
COPY --chown=app:app . .

COPY --chown=app:app docker/django-entrypoint.sh /app/docker/django-entrypoint.sh
RUN chmod +x /app/docker/django-entrypoint.sh

RUN mkdir -p /var/log/celery /app/staticfiles \
    && python manage.py collectstatic --noinput \
    && chown -R app:app /app/staticfiles /var/log/celery

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/clusters/tabs/')" || exit 1

CMD ["gunicorn", "core.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "2"]


# Optional: local HuggingFace embeddings (dev profile or dedicated worker).
FROM runtime AS embeddings

USER root

COPY requirements-embeddings.txt /tmp/requirements-embeddings.txt
# --index-url replaces PyPI for torch so pip cannot pick CUDA wheels from pypi.org.
RUN pip install --no-cache-dir \
      --index-url https://download.pytorch.org/whl/cpu \
      'torch>=2.1.0,<3' \
    && pip install --no-cache-dir -r /tmp/requirements-embeddings.txt \
    && rm /tmp/requirements-embeddings.txt

USER app
