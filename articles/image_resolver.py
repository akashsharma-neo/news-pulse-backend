"""
Resolve article and cluster display images from scrape metadata and tab placeholders.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from django.conf import settings

if TYPE_CHECKING:
    from articles.models import Article

PLACEHOLDER_BY_SLUG: dict[str, str] = {
    "india": "india.jpg",
    "sports": "sports.jpg",
    "business": "business.jpg",
    "global": "global.jpg",
    "just-for-you": "personal.jpg",
}

DEFAULT_PLACEHOLDER = "default.jpg"
MAX_IMAGE_URL_LEN = 2048


def validate_image_url(url: str | None) -> str | None:
    """Return url if it is a safe https image URL, else None."""
    if not url or not isinstance(url, str):
        return None
    url = url.strip()
    if len(url) > MAX_IMAGE_URL_LEN:
        return None
    parsed = urlparse(url)
    if parsed.scheme != "https":
        return None
    if parsed.netloc == "":
        return None
    lowered = url.lower()
    if lowered.startswith("javascript:") or lowered.startswith("data:"):
        return None
    return url


def _img_src_from_tag(img) -> str | None:
    for attr in ("src", "data-src", "data-original", "data-lazy-src"):
        val = img.get(attr)
        if val and str(val).strip():
            return str(val).strip()
    return None


def _resolve_relative(url: str, base_url: str | None) -> str:
    if not base_url:
        return url
    if url.startswith("//"):
        parsed = urlparse(base_url)
        scheme = parsed.scheme or "https"
        return f"{scheme}:{url}"
    if url.startswith("/") or not urlparse(url).scheme:
        return urljoin(base_url, url)
    return url


def extract_rss_image(entry) -> str | None:
    """Extract lead image URL from a feedparser entry."""
    if hasattr(entry, "media_thumbnail") and entry.media_thumbnail:
        url = entry.media_thumbnail[0].get("url")
        validated = validate_image_url(url)
        if validated:
            return validated

    if hasattr(entry, "media_content") and entry.media_content:
        for media in entry.media_content:
            media_type = (media.get("type") or "").lower()
            if media_type.startswith("image") or not media_type:
                validated = validate_image_url(media.get("url"))
                if validated:
                    return validated

    for enc in getattr(entry, "enclosures", []) or []:
        enc_type = (enc.get("type") or "").lower()
        if enc_type.startswith("image"):
            href = enc.get("href") or enc.get("url")
            validated = validate_image_url(href)
            if validated:
                return validated

    for field in ("summary", "description", "content"):
        html = ""
        if field == "content" and hasattr(entry, "content") and entry.content:
            html = entry.content[0].get("value", "")
        else:
            html = entry.get(field, "") if hasattr(entry, "get") else getattr(entry, field, "")
        if html and "<img" in str(html).lower():
            soup = BeautifulSoup(html, "html.parser")
            for img in soup.find_all("img"):
                src = _img_src_from_tag(img)
                if src:
                    validated = validate_image_url(_resolve_relative(src, entry.get("link")))
                    if validated:
                        return validated

    return None


def extract_web_image(container, base_url: str | None = None) -> str | None:
    """Extract lead image URL from a web listing container element."""
    for img in container.find_all("img"):
        src = _img_src_from_tag(img)
        if not src:
            continue
        resolved = _resolve_relative(src, base_url)
        validated = validate_image_url(resolved)
        if validated:
            return validated
    return None


def placeholder_filename(category_slug: str | None) -> str:
    if not category_slug:
        return DEFAULT_PLACEHOLDER
    return PLACEHOLDER_BY_SLUG.get(category_slug.strip().lower(), DEFAULT_PLACEHOLDER)


def build_placeholder_url(filename: str) -> str:
    base = getattr(settings, "PLACEHOLDER_BASE_URL", "").strip()
    if base:
        return f"{base.rstrip('/')}/{filename}"
    site_base = getattr(settings, "BASE_URL", "http://localhost:8000").rstrip("/")
    static_url = getattr(settings, "STATIC_URL", "/static/").strip("/")
    return f"{site_base}/{static_url}/newspulse/placeholders/{filename}"


def placeholder_url(category_slug: str | None) -> str:
    return build_placeholder_url(placeholder_filename(category_slug))


def pick_cluster_image(
    articles: list[Article],
    primary: Article,
    category_slug: str | None,
) -> str:
    """Pick display image: primary first, then siblings, else tab placeholder."""
    ordered: list[Article] = [primary]
    primary_pk = primary.pk
    for article in articles:
        if article.pk != primary_pk:
            ordered.append(article)

    for article in ordered:
        validated = validate_image_url(article.source_image_url)
        if validated:
            return validated

    return placeholder_url(category_slug)


def resolve_cluster_display_image(cluster) -> str:
    """API fallback: cluster.image_url → primary.source_image_url → placeholder."""
    validated = validate_image_url(cluster.image_url)
    if validated:
        return validated

    primary = cluster.primary_article
    if primary:
        validated = validate_image_url(primary.source_image_url)
        if validated:
            return validated
        category_slug = None
        if primary.source and primary.source.category:
            category_slug = primary.source.category.slug
        return placeholder_url(category_slug)

    return placeholder_url(None)
