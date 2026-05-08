"""Local embedding pipeline for NewsPulse.

Generates dense vector embeddings for article summaries and article text using
a local ``sentence-transformers`` model. Embeddings are written back to the
PostgreSQL ``pgvector`` column on ``Article.embedding``.

Supported models
----------------
- ``all-mpnet-base-v2`` — 768-dim (default, best quality)
- ``all-MiniLM-L6-v2``  — 384-dim (faster, smaller)

Usage
-----
    from worker.embeddings import generate_embeddings, embed_text

    # Embed a single text string
    vec = embed_text("India wins the World Cup final")

    # Batch-embed all articles missing embeddings
    generate_embeddings(batch_size=64)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Iterator

import numpy as np
from django.db import transaction
from sentence_transformers import SentenceTransformer
from tqdm.auto import tqdm

from articles.models import Article

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model cache (singleton across calls)
# ---------------------------------------------------------------------------

_MODEL_CACHE: dict[str, SentenceTransformer] = {}
_MODEL_PATH = Path(os.environ.get(
    "EMBEDDING_MODEL_PATH",
    str(Path.home() / ".cache" / "huggingface" / "sentence-transformers"),
))


def _get_model(model_name: str = "all-mpnet-base-v2") -> SentenceTransformer:
    """Load (or return cached) a sentence-transformers model.

    Args:
        model_name: HuggingFace model identifier.

    Returns:
        A ``SentenceTransformer`` instance ready for inference.
    """
    if model_name not in _MODEL_CACHE:
        logger.info("Loading embedding model '%s' …", model_name)
        _MODEL_CACHE[model_name] = SentenceTransformer(model_name)
    return _MODEL_CACHE[model_name]


# ---------------------------------------------------------------------------
# Text → vector helpers
# ---------------------------------------------------------------------------


def embed_text(
    text: str,
    model_name: str = "all-mpnet-base-v2",
) -> list[float]:
    """Generate a single embedding vector for *text*.

    Args:
        text: Input text to embed.
        model_name: HuggingFace model identifier.

    Returns:
        A list of floats representing the dense embedding.
    """
    model = _get_model(model_name)
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


def embed_texts(
    texts: list[str],
    model_name: str = "all-mpnet-base-v2",
    batch_size: int = 64,
) -> np.ndarray:
    """Batch-encode a list of texts into embedding vectors.

    Args:
        texts: List of text strings to embed.
        model_name: HuggingFace model identifier.
        batch_size: How many texts to encode per model forward pass.

    Returns:
        A ``(N, D)`` numpy array of normalized embeddings.
    """
    model = _get_model(model_name)
    return model.encode(texts, normalize_embeddings=True, batch_size=batch_size)


# ---------------------------------------------------------------------------
# Database operations
# ---------------------------------------------------------------------------


def _update_article_embedding(
    article: Article,
    vector: list[float],
) -> None:
    """Persist an embedding vector to an Article instance.

    Args:
        article: The Article to update.
        vector: Normalized embedding list.
    """
    article.embedding = vector
    article.save(update_fields=["embedding"])


@transaction.atomic
def generate_embeddings(
    model_name: str = "all-mpnet-base-v2",
    batch_size: int = 64,
    field: str = "summary",
) -> dict:
    """Generate and store embeddings for articles missing vectors.

    Walks through all ``Article`` rows whose ``embedding`` is NULL,
    builds text from the chosen *field* (default: ``summary``; falls back
    to ``title`` if the field is empty), embeds in batches, and writes
    results back to PostgreSQL.

    Args:
        model_name: HuggingFace model identifier.
        batch_size: Articles per model forward pass.
        field: Model field to embed — ``summary``, ``title``, or ``full_text``.

    Returns:
        Dict with counts:
        ``{"generated": N, "skipped_empty": N, "updated": N}``
    """
    # Articles without embeddings, ordered oldest first
    articles = list(
        Article.objects.filter(embedding__isnull=True)
        .order_by("fetched_at")
    )

    if not articles:
        logger.info("No articles need embeddings")
        return {"generated": 0, "skipped_empty": 0, "updated": 0}

    logger.info(
        "Generating embeddings for %d articles (model=%s, field=%s)",
        len(articles), model_name, field,
    )

    model = _get_model(model_name)
    dim = getattr(model, "get_embedding_dimension", model.get_sentence_embedding_dimension)()

    generated = 0
    skipped_empty = 0
    updated = 0

    # Process in batches
    for i in range(0, len(articles), batch_size):
        batch = articles[i : i + batch_size]

        # Build text for each article
        texts: list[str] = []
        for article in batch:
            text = getattr(article, field, "")
            if not text or not text.strip():
                # Fall back to title
                text = article.title
            if not text or not text.strip():
                skipped_empty += 1
                continue
            texts.append(text)

        if not texts:
            continue

        # Batch encode
        vectors = model.encode(texts, normalize_embeddings=True, batch_size=32)

        # Write back
        for article, vector in zip(batch, vectors):
            # Skip if already embedded (might have been updated by another
            # process in the same batch window)
            if article.embedding is not None:
                continue

            if not texts:
                continue

            # Find index of this article in texts list
            text = getattr(article, field, "") or article.title
            try:
                idx = texts.index(text)
            except ValueError:
                idx = 0  # fallback

            vec_list = vector[idx].tolist() if vector.ndim > 1 else vector.tolist()
            if len(vec_list) != dim:
                logger.warning(
                    "Dimension mismatch for article %d: got %d, expected %d",
                    article.id, len(vec_list), dim,
                )
                continue

            _update_article_embedding(article, vec_list)
            generated += 1
            updated += 1

    logger.info(
        "Embedding generation done: generated=%d skipped=%d updated=%d",
        generated, skipped_empty, updated,
    )
    return {
        "generated": generated,
        "skipped_empty": skipped_empty,
        "updated": updated,
    }


@transaction.atomic
def generate_cluster_embeddings(
    model_name: str = "all-mpnet-base-v2",
    batch_size: int = 64,
) -> dict:
    """Generate embeddings for TopicCluster summaries.

    Creates a synthetic Article-like text from each cluster's summary +
    source names, then stores the embedding on the primary article.

    Args:
        model_name: HuggingFace model identifier.
        batch_size: Clusters per model forward pass.

    Returns:
        Dict with counts: ``{"generated": N, "updated": N}``
    """
    from articles.models import TopicCluster

    clusters = list(
        TopicCluster.objects.filter(primary_article__embedding__isnull=True)
        .order_by("-created_at")
    )

    if not clusters:
        logger.info("No clusters need embeddings")
        return {"generated": 0, "updated": 0}

    logger.info(
        "Generating embeddings for %d clusters (model=%s)",
        len(clusters), model_name,
    )

    model = _get_model(model_name)
    dim = getattr(model, "get_embedding_dimension", model.get_sentence_embedding_dimension)()

    generated = 0
    updated = 0

    for i in range(0, len(clusters), batch_size):
        batch = clusters[i : i + batch_size]

        texts: list[str] = []
        articles: list[Article] = []
        for cluster in batch:
            text = cluster.summary
            if text:
                # Append source names for richer context
                sources = cluster.source_names()
                if sources:
                    text = text + " | Sources: " + ", ".join(sources)
            if not text or not text.strip():
                text = cluster.primary_article.title
            texts.append(text)
            articles.append(cluster.primary_article)

        if not texts:
            continue

        vectors = model.encode(texts, normalize_embeddings=True, batch_size=32)

        for article, vector in zip(articles, vectors):
            if article.embedding is not None:
                continue

            vec_list = vector.tolist()
            if len(vec_list) != dim:
                logger.warning(
                    "Dim mismatch for article %d: got %d, expected %d",
                    article.id, len(vec_list), dim,
                )
                continue

            _update_article_embedding(article, vec_list)
            generated += 1
            updated += 1

    logger.info(
        "Cluster embedding done: generated=%d updated=%d",
        generated, updated,
    )
    return {"generated": generated, "updated": updated}
