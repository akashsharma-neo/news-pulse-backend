"""Canonical article URL normalization for scrape-time deduplication."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Tracking / session params stripped before comparing or storing URLs.
_STRIP_QUERY_PREFIXES = ("utm_",)
_STRIP_QUERY_KEYS = frozenset(
    {
        "fbclid",
        "gclid",
        "mc_cid",
        "mc_eid",
        "ref",
        "ref_src",
        "igshid",
    }
)


def normalize_article_url(url: str) -> str:
    """Return a stable URL for deduplication (scheme/host/path/query cleanup).

    - Lowercases scheme and host; strips leading ``www.``
    - Removes trailing slash on paths (except root ``/``)
    - Drops common tracking query params
    - Removes URL fragments
    """
    raw = (url or "").strip()
    if not raw:
        return raw

    parsed = urlparse(raw)
    scheme = (parsed.scheme or "https").lower()
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]

    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")

    kept_pairs: list[tuple[str, str]] = []
    for key, value in parse_qsl(parsed.query, keep_blank_values=False):
        lower = key.lower()
        if lower in _STRIP_QUERY_KEYS:
            continue
        if any(lower.startswith(prefix) for prefix in _STRIP_QUERY_PREFIXES):
            continue
        kept_pairs.append((key, value))
    kept_pairs.sort()
    query = urlencode(kept_pairs, doseq=True)

    return urlunparse((scheme, netloc, path, "", query, ""))


def article_exists_for_url(url: str) -> bool:
    """True if an Article row already exists for this URL (normalized or legacy raw)."""
    from articles.models import Article

    normalized = normalize_article_url(url)
    if Article.objects.filter(url=normalized).exists():
        return True
    stripped = (url or "").strip()
    if stripped and stripped != normalized and Article.objects.filter(url=stripped).exists():
        return True
    return False
