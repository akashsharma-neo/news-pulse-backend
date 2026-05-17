"""
Helpers for scraping and summarizing article body text.

Listing pages often expose only a deck or first paragraph; we join multiple
paragraphs on listings and optionally fetch the article URL for full text.
"""

from __future__ import annotations

import re
from typing import Callable

from bs4 import BeautifulSoup

MIN_BODY_WORDS = 80
MAX_BODY_CHARS = 8000
MAX_SUMMARY_SOURCE_CHARS = 6000


def word_count(text: str) -> int:
    return len(text.split())


def html_to_plain_text(html: str) -> str:
    """Strip HTML tags and collapse whitespace."""
    if not html:
        return ""
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def extract_listing_content(container, content_selectors: list[str]) -> str:
    """
    Extract body text from a listing/card container.

    Joins all matching paragraph-like elements instead of only the first match
    (which is often a one-line deck).
    """
    paragraphs: list[str] = []
    seen: set[str] = set()

    for sel in content_selectors:
        for el in container.select(sel):
            text = el.get_text(separator=" ", strip=True)
            if len(text) < 25:
                continue
            key = text[:120]
            if key in seen:
                continue
            seen.add(key)
            paragraphs.append(text)
        if paragraphs:
            break

    if not paragraphs:
        text = container.get_text(separator=" ", strip=True)
        return re.sub(r"\s+", " ", text)[:MAX_BODY_CHARS]

    combined = " ".join(paragraphs)
    return re.sub(r"\s+", " ", combined)[:MAX_BODY_CHARS]


def extract_article_page_content(html: str, config: dict | None = None) -> str:
    """Extract main article body from an article detail page."""
    config = config or {}
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside"]):
        tag.decompose()

    content_selectors = [
        s.strip()
        for s in config.get(
            "selector_content",
            "article, [class*='article-body'], [class*='story-body'], main",
        ).split(",")
        if s.strip()
    ]

    roots = []
    for sel in content_selectors:
        roots.extend(soup.select(sel))
    if not roots:
        roots = [soup.body] if soup.body else []

    paragraphs: list[str] = []
    seen: set[str] = set()
    for root in roots[:3]:
        for el in root.select("p"):
            text = el.get_text(separator=" ", strip=True)
            if len(text) < 40:
                continue
            key = text[:120]
            if key in seen:
                continue
            seen.add(key)
            paragraphs.append(text)

    if not paragraphs:
        for root in roots[:1]:
            text = root.get_text(separator=" ", strip=True)
            if word_count(text) >= MIN_BODY_WORDS:
                return re.sub(r"\s+", " ", text)[:MAX_BODY_CHARS]

    combined = " ".join(paragraphs)
    return re.sub(r"\s+", " ", combined)[:MAX_BODY_CHARS]


def extract_rss_entry_content(entry) -> str:
    """Best-effort plain text from an RSS/Atom entry."""
    if getattr(entry, "content", None):
        parts = []
        for block in entry.content:
            value = block.get("value", "") if isinstance(block, dict) else getattr(block, "value", "")
            if value:
                parts.append(html_to_plain_text(value))
        if parts:
            return " ".join(parts)[:MAX_BODY_CHARS]

    for key in ("summary", "description", "subtitle"):
        raw = entry.get(key, "") if hasattr(entry, "get") else ""
        if raw:
            return html_to_plain_text(raw)[:MAX_BODY_CHARS]
    return ""


def enrich_article_content(
    url: str,
    listing_content: str,
    config: dict | None,
    fetch_html: Callable[[str], str | None],
) -> str:
    """
    Return article body text, fetching the article URL when listing/RSS text is thin.
    """
    content = (listing_content or "").strip()
    if word_count(content) >= MIN_BODY_WORDS:
        return content[:MAX_BODY_CHARS]

    html = fetch_html(url)
    if not html:
        return content[:MAX_BODY_CHARS]

    page_content = extract_article_page_content(html, config)
    if word_count(page_content) > word_count(content):
        return page_content
    return content[:MAX_BODY_CHARS]


def gather_articles_for_summary(primary, related_articles: list) -> str:
    """Build source material for cluster summarization from primary + related articles."""
    blocks: list[str] = []

    def add_block(article, label: str) -> None:
        title = (article.title or "").strip()
        body = (article.full_text or "").strip()
        source = article.source.name if article.source else "Unknown"
        if not body and title:
            body = title
        if not title and not body:
            return
        blocks.append(
            f"[{label} — {source}]\nTitle: {title}\n{body[:2500]}"
        )

    add_block(primary, "Primary")
    for idx, article in enumerate(related_articles[:3], start=1):
        add_block(article, f"Related {idx}")

    combined = "\n\n".join(blocks)
    return combined[:MAX_SUMMARY_SOURCE_CHARS]


def build_summarize_prompt(
    *,
    title: str,
    source_name: str,
    url: str,
    source_material: str,
    source_names: list[str],
) -> str:
    extra_sources = ""
    if len(source_names) > 1:
        extra_sources = (
            f"\nThis story is covered by multiple outlets: {', '.join(source_names)}. "
            "Synthesize the shared facts across the material below when possible."
        )

    return (
        "Write an InShorts-style news digest in exactly 2 or 3 complete sentences, "
        "total length between 60 and 80 words. "
        "Include the key facts: who, what, where, and why it matters. "
        "Do not repeat the headline verbatim. "
        "Do not use bullet points or labels. "
        "Start directly with the summary — no preamble like 'Here is a summary'."
        f"{extra_sources}\n\n"
        f"Headline: {title}\n"
        f"Primary source: {source_name}\n"
        f"URL: {url}\n\n"
        f"Source material:\n{source_material}"
    )


def is_summary_too_short(summary: str, min_words: int = 40) -> bool:
    return word_count(summary.strip()) < min_words
