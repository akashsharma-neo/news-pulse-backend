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
MAX_SUMMARY_SOURCE_CHARS = 2500
MAX_SUMMARY_ARTICLE_CHARS = 1000
MAX_RELATED_ARTICLES_FOR_SUMMARY = 4

TARGET_SUMMARY_WORDS_MIN = 100
TARGET_SUMMARY_WORDS_MAX = 120
TARGET_SUMMARY_FALLBACK_WORDS = 120
SUMMARY_MIN_ACCEPT_WORDS = 85

# Boilerplate lines common on paywalled / login-gated publisher pages.
JUNK_LINE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"subscribe to (continue|read|the hindu|access)",
        r"sign in|log in|login to|register to read",
        r"already have an account",
        r"exclusive(ly)? for (our )?subscribers",
        r"premium (subscriber|member|content)",
        r"this (story|article) is (for|available to) premium",
        r"enable javascript",
        r"cookie(s)? (policy|consent|preferences)",
        r"click here to (continue|read)",
        r"you have reached your (free )?article limit",
    )
)


def word_count(text: str) -> int:
    if not text:
        return 0
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


def is_junk_paragraph(text: str) -> bool:
    """True when a paragraph is likely paywall/login/cookie boilerplate."""
    stripped = (text or "").strip()
    if not stripped:
        return True
    lower = stripped.lower()
    for pattern in JUNK_LINE_PATTERNS:
        if pattern.search(lower):
            return True
    return False


def clean_article_text(text: str, source_name: str | None = None) -> str:
    """
    Normalize scraped or RSS text to plain news copy.

    Strips HTML, removes paywall/login boilerplate lines, collapses whitespace.
    """
    del source_name  # reserved for source-specific rules later
    plain = html_to_plain_text(text or "")
    if not plain:
        return ""

    # Split on sentence boundaries and newlines; drop junk fragments.
    parts = re.split(r"(?<=[.!?])\s+|\n+", plain)
    kept: list[str] = []
    for part in parts:
        part = part.strip()
        if not part or is_junk_paragraph(part):
            continue
        kept.append(part)

    if kept:
        return re.sub(r"\s+", " ", " ".join(kept)).strip()

    # If everything was filtered, return de-HTML'd text without line filtering.
    return plain


def _junk_word_ratio(text: str) -> float:
    words = text.lower().split()
    if not words:
        return 1.0
    junk = 0
    for word in words:
        for pattern in JUNK_LINE_PATTERNS:
            if pattern.search(word):
                junk += 1
                break
    return junk / len(words)


def is_usable_article_body(text: str, source_name: str | None = None) -> bool:
    """True when cleaned text looks like real article content."""
    cleaned = clean_article_text(text, source_name)
    wc = word_count(cleaned)
    if wc < 40:
        return False
    if _junk_word_ratio(cleaned) > 0.25:
        return False
    # First sentence should not be entirely junk.
    first = re.split(r"(?<=[.!?])\s+", cleaned, maxsplit=1)[0]
    if first and is_junk_paragraph(first):
        return False
    return True


def body_quality_score(text: str, source_name: str | None = None) -> int:
    """Higher is better for choosing RSS vs page-fetch candidates."""
    cleaned = clean_article_text(text, source_name)
    if not is_usable_article_body(cleaned, source_name):
        return word_count(cleaned) // 4
    return word_count(cleaned)


def truncate_at_sentence_boundary(text: str, max_words: int = TARGET_SUMMARY_FALLBACK_WORDS) -> str:
    """Trim to max_words without cutting mid-sentence when possible."""
    cleaned = clean_article_text(text)
    if not cleaned:
        return ""
    words = cleaned.split()
    if len(words) <= max_words:
        return cleaned

    truncated = " ".join(words[:max_words])
    last_stop = max(truncated.rfind("."), truncated.rfind("!"), truncated.rfind("?"))
    if last_stop > len(truncated) // 3:
        return truncated[: last_stop + 1].strip()
    return truncated.rstrip(".,;:") + "..."


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
            if len(text) < 25 or is_junk_paragraph(text):
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
        return clean_article_text(re.sub(r"\s+", " ", text)[:MAX_BODY_CHARS])

    combined = " ".join(paragraphs)
    return clean_article_text(re.sub(r"\s+", " ", combined)[:MAX_BODY_CHARS])


def _decompose_excluded_nodes(soup: BeautifulSoup, config: dict) -> None:
    exclude = config.get("exclude_selectors", "")
    if not exclude:
        return
    for sel in (s.strip() for s in exclude.split(",") if s.strip()):
        for node in soup.select(sel):
            node.decompose()


def extract_article_page_content(html: str, config: dict | None = None) -> str:
    """Extract main article body from an article detail page."""
    config = config or {}
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside"]):
        tag.decompose()
    _decompose_excluded_nodes(soup, config)

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
            if len(text) < 40 or is_junk_paragraph(text):
                continue
            key = text[:120]
            if key in seen:
                continue
            seen.add(key)
            paragraphs.append(text)

    if not paragraphs:
        for root in roots[:1]:
            text = root.get_text(separator=" ", strip=True)
            cleaned = clean_article_text(text)
            if word_count(cleaned) >= MIN_BODY_WORDS:
                return cleaned[:MAX_BODY_CHARS]

    combined = " ".join(paragraphs)
    return clean_article_text(combined)[:MAX_BODY_CHARS]


def extract_rss_entry_content(entry) -> str:
    """Best-effort plain text from an RSS/Atom entry."""
    if getattr(entry, "content", None):
        parts = []
        for block in entry.content:
            value = block.get("value", "") if isinstance(block, dict) else getattr(block, "value", "")
            if value:
                parts.append(html_to_plain_text(value))
        if parts:
            return clean_article_text(" ".join(parts)[:MAX_BODY_CHARS])

    for key in ("summary", "description", "subtitle"):
        raw = entry.get(key, "") if hasattr(entry, "get") else ""
        if raw:
            return clean_article_text(html_to_plain_text(raw)[:MAX_BODY_CHARS])
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
    config = config or {}
    listing_clean = clean_article_text(listing_content or "")
    prefer_rss = config.get("prefer_rss_body", False)

    if word_count(listing_clean) >= MIN_BODY_WORDS and is_usable_article_body(listing_clean):
        return listing_clean[:MAX_BODY_CHARS]

    if prefer_rss and is_usable_article_body(listing_clean):
        return listing_clean[:MAX_BODY_CHARS]

    html = fetch_html(url)
    if not html:
        return listing_clean[:MAX_BODY_CHARS]

    page_content = extract_article_page_content(html, config)
    listing_score = body_quality_score(listing_clean)
    page_score = body_quality_score(page_content)

    if page_score > listing_score and is_usable_article_body(page_content):
        return page_content
    if is_usable_article_body(listing_clean):
        return listing_clean[:MAX_BODY_CHARS]
    if is_usable_article_body(page_content):
        return page_content
    # Last resort: whichever has more words after cleaning.
    if word_count(page_content) > word_count(listing_clean):
        return page_content
    return listing_clean[:MAX_BODY_CHARS]


def fallback_summary_from_article(article) -> str:
    """Short excerpt from article text when LLM summarization is skipped."""
    if not article:
        return "Summary pending."
    if article.summary:
        return clean_article_text(article.summary)
    text = clean_article_text(article.full_text or "")
    if text and not is_junk_paragraph(text):
        if word_count(text) <= TARGET_SUMMARY_FALLBACK_WORDS:
            return text
        if is_usable_article_body(text):
            return truncate_at_sentence_boundary(text, TARGET_SUMMARY_FALLBACK_WORDS)
        return truncate_at_sentence_boundary(text, TARGET_SUMMARY_FALLBACK_WORDS)
    title = (article.title or "").strip()
    return title or "Summary pending."


def gather_articles_for_summary(
    primary,
    related_articles: list,
    source_names: list[str] | None = None,
    max_related: int | None = None,
) -> str:
    """Build source material for cluster summarization from primary + related articles."""
    blocks: list[str] = []
    names = source_names or []
    if max_related is None:
        max_related = (
            MAX_RELATED_ARTICLES_FOR_SUMMARY
            if len(names) > 1
            else 0
        )

    def add_block(article, label: str) -> None:
        title = (article.title or "").strip()
        source = article.source.name if article.source else "Unknown"
        body = clean_article_text(article.full_text or "", source)
        if not body and title:
            body = title
        if not title and not body:
            return
        if body and is_junk_paragraph(body):
            return
        if body and word_count(body) < 10:
            return
        blocks.append(
            f"[{label} — {source}]\nTitle: {title}\n{body[:MAX_SUMMARY_ARTICLE_CHARS]}"
        )

    add_block(primary, "Primary")
    added = 0
    for idx, article in enumerate(related_articles):
        if added >= max_related:
            break
        before = len(blocks)
        add_block(article, f"Related {idx + 1}")
        if len(blocks) > before:
            added += 1

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
        f"Write an InShorts-style news digest in 3 or 4 complete sentences, "
        f"total length between {TARGET_SUMMARY_WORDS_MIN} and {TARGET_SUMMARY_WORDS_MAX} words. "
        "Include the key facts: who, what, where, and why it matters. "
        "End with a complete sentence — do not cut off mid-thought. "
        "Do not repeat the headline verbatim. "
        "Do not use bullet points or labels. "
        "Start directly with the summary — no preamble like 'Here is a summary'."
        f"{extra_sources}\n\n"
        f"Headline: {title}\n"
        f"Primary source: {source_name}\n"
        f"URL: {url}\n\n"
        f"Source material:\n{source_material}"
    )


def is_summary_too_short(summary: str, min_words: int = SUMMARY_MIN_ACCEPT_WORDS) -> bool:
    return word_count(clean_article_text(summary)) < min_words
