"""
NewsPulse environment profiles.

Set NEWSMINE_ENV to dev | staging | prod (default: dev).
Profile defaults apply only when the corresponding env var is not already set.
Explicit values in .env or docker-compose always win.
"""

from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

VALID_ENVS = frozenset({"dev", "staging", "prod"})

PROFILES: dict[str, dict[str, str]] = {
    "dev": {
        "OPENAI_COMPATIBLE_BASE_URL": "http://host.docker.internal:1234/v1",
        "OPENAI_COMPATIBLE_MODEL": "google/gemma-4-e4b",
        "OPENAI_COMPATIBLE_API_KEY": "lm-studio",
        "DJANGO_DEBUG": "true",
        "BASE_URL": "http://localhost:8000",
        "CORS_ALLOWED_ORIGINS": "http://localhost:3000,http://127.0.0.1:3000",
        "DJANGO_ALLOWED_HOSTS": "localhost,127.0.0.1,0.0.0.0",
        "SUMMARIZE_BATCH_SIZE": "50",
        "SUMMARIZE_DELAY_SEC": "0",
        "SUMMARIZE_FETCH_FULL_BODY": "true",
        "SUMMARIZE_ENABLED": "false",
        "EMBEDDINGS_ENABLED": "false",
    },
    "staging": {
        "OPENAI_COMPATIBLE_BASE_URL": "https://openrouter.ai/api/v1",
        "OPENAI_COMPATIBLE_MODEL": "meta-llama/llama-3.1-8b-instruct",
        "EMBEDDINGS_ENABLED": "false",
        "SUMMARIZE_FETCH_FULL_BODY": "false",
    },
    "prod": {
        "OPENAI_COMPATIBLE_BASE_URL": "https://openrouter.ai/api/v1",
        "OPENAI_COMPATIBLE_MODEL": "meta-llama/llama-3.1-8b-instruct",
        "EMBEDDINGS_ENABLED": "false",
        "SUMMARIZE_FETCH_FULL_BODY": "false",
    },
}


def _load_dotenv() -> None:
    env_file = BASE_DIR / ".env"
    if not env_file.is_file():
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(env_file, override=False)
    except ImportError:
        pass


def get_newsmine_env() -> str:
    raw = os.environ.get("NEWSMINE_ENV", "dev").strip().lower()
    if raw not in VALID_ENVS:
        return "dev"
    return raw


def apply_profile() -> str:
    """Apply profile defaults for the active NEWSMINE_ENV. Returns active env name."""
    _load_dotenv()
    active = get_newsmine_env()
    os.environ.setdefault("NEWSMINE_ENV", active)
    for key, value in PROFILES.get(active, {}).items():
        os.environ.setdefault(key, value)
    return active


def get_active_profile() -> dict[str, str]:
    """Non-secret snapshot of the active profile defaults (for logging/docs)."""
    active = get_newsmine_env()
    return dict(PROFILES.get(active, {}))
