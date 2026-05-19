# ===========================
# NewsPulse — Multi-stage Dockerfile
# ===========================
# Stage 1: Builder (install deps)
# Stage 2: Runtime (lean image)
#
# NOTE: torch is installed CPU-only (no CUDA).
# sentence-transformers needs torch, but we pin the CPU wheel first
# so pip doesn't pull in 400MB of CUDA libs.

FROM python:3.14-slim AS builder

WORKDIR /build

# System deps for pgvector C extension + psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 1) CPU-only torch first (no CUDA, ~200MB vs ~400MB)
RUN pip install --no-cache-dir --prefix=/install torch>=2.1.0 --index-url https://download.pytorch.org/whl/cpu

# 2) Install everything else from requirements.txt WITHOUT resolving deps
#    (torch is already installed, this won't reinstall it)
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install --no-deps \
    $(cat requirements.txt | xargs)

# 3) Install sentence-transformers, transformers, huggingface-hub etc.
#    They'll see torch is already installed and won't reinstall it.
#    We install them separately to get their non-torch deps.
RUN pip install --no-cache-dir --prefix=/install \
    sentence-transformers \
    transformers \
    huggingface-hub \
    safetensors \
    tokenizers \
    tqdm \
    h11 \
    httpx \
    fsspec \
    filelock \
    hf-xet \
    annotated-doc \
    typer \
    shellingham \
    rich \
    pygments \
    pydantic \
    markdown-it-py \
    mdurl \
    click \
    click-didyoumean \
    click-plugins \
    click-repl \
    typing-extensions \
    jinja2 \
    markupsafe \
    sympy \
    mpmath \
    networkx \
    threadpoolctl \
    scipy \
    scikit-learn \
    joblib \
    regex \
    numpy


# --- Runtime ---
FROM python:3.14-slim

# Non-root user
RUN groupadd -r app && useradd -r -g app -d /app -s /sbin/nologin app

WORKDIR /app

# System deps (libpq for psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy project code
COPY --chown=app:app . .

# Dev/prod: migrate before gunicorn when entrypoint is used
COPY --chown=app:app docker/django-entrypoint.sh /app/docker/django-entrypoint.sh
RUN chmod +x /app/docker/django-entrypoint.sh

# Log dir, collect static for WhiteNoise + Gunicorn (no runserver static serving)
RUN mkdir -p /var/log/celery /app/staticfiles \
&& python manage.py collectstatic --noinput \
    && chown -R app:app /app/staticfiles /var/log/celery

USER app

# Expose Django port
EXPOSE 8000

# Healthcheck
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/clusters/tabs/')" || exit 1

# Default: run Django (gunicorn)
CMD ["gunicorn", "core.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "2"]
