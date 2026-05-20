"""
Generate and validate Nex tap-to-ask questions for topic clusters.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

MAX_PROMPTS = 3
MAX_PROMPT_CHARS = 120
MAX_WORDS_PER_PROMPT = 12

_FALLBACK_TEMPLATES = (
    "What are the main facts in this story?",
    "Who is most affected by this?",
    "What might happen next?",
)


def build_nex_prompts_request(
    *,
    title: str,
    summary: str,
    category_slug: str,
    source_names: list[str],
) -> str:
    """Build the user message for the Nex suggestions LLM call."""
    sources = ", ".join(source_names[:6]) if source_names else "unknown"
    return (
        "You suggest short questions a news reader would tap to learn more about one story.\n"
        "Return ONLY a JSON array of exactly 3 strings. Each string is one question, "
        f"at most {MAX_WORDS_PER_PROMPT} words, no markdown, no numbering.\n"
        "Mix: (1) key facts, (2) who is affected or involved, (3) what could happen next.\n"
        "Questions must be answerable from the summary below (do not ask to search the web).\n"
        "Use specific names/places from the story when present.\n\n"
        f"Tab: {category_slug}\n"
        f"Sources: {sources}\n"
        f"Headline: {title}\n"
        f"Summary: {summary}\n"
    )


def parse_nex_prompts_response(raw: str) -> list[str] | None:
    """Parse LLM output into up to 3 validated question strings."""
    text = (raw or "").strip()
    if not text:
        return None

    # Strip optional markdown code fence
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Try to extract a JSON array substring
        match = re.search(r"\[[\s\S]*\]", text)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None

    if not isinstance(data, list):
        return None

    return _normalize_prompt_list(data)


def _normalize_prompt_list(items: list[Any]) -> list[str] | None:
    prompts: list[str] = []
    for item in items:
        if not isinstance(item, str):
            continue
        q = " ".join(item.strip().split())
        if not q:
            continue
        if not q.endswith("?"):
            q = q.rstrip(".!") + "?"
        if len(q) > MAX_PROMPT_CHARS:
            q = q[: MAX_PROMPT_CHARS - 1].rstrip() + "?"
        words = q.split()
        if len(words) > MAX_WORDS_PER_PROMPT:
            q = " ".join(words[:MAX_WORDS_PER_PROMPT])
            if not q.endswith("?"):
                q += "?"
        if q and q not in prompts:
            prompts.append(q)
        if len(prompts) >= MAX_PROMPTS:
            break

    return prompts if len(prompts) == MAX_PROMPTS else None


def fallback_nex_prompts(title: str) -> list[str]:
    """Deterministic questions when LLM generation or parsing fails."""
    topic = _short_topic_from_title(title)
    if topic:
        return [
            f"What is the core update on {topic}?",
            f"Who is most affected by {topic}?",
            f"What could happen next with {topic}?",
        ]
    return list(_FALLBACK_TEMPLATES)


def _short_topic_from_title(title: str) -> str:
    """Extract a short topic phrase from a headline for fallback templates."""
    t = (title or "").strip()
    if not t:
        return ""
    # Drop trailing source-style suffix after em dash or pipe
    for sep in (" — ", " – ", " | ", " - "):
        if sep in t:
            t = t.split(sep)[0].strip()
    words = t.split()
    if len(words) > 8:
        t = " ".join(words[:8])
    return t.rstrip("?.!,")


def generate_nex_prompts_for_cluster(
    client: Any,
    model: str,
    *,
    title: str,
    summary: str,
    category_slug: str,
    source_names: list[str],
    max_tokens: int = 150,
) -> list[str]:
    """
    Call the LLM to produce 3 Nex questions; return fallback on any failure.
    """
    if not (summary or "").strip():
        return fallback_nex_prompts(title)

    prompt = build_nex_prompts_request(
        title=title,
        summary=summary,
        category_slug=category_slug or "news",
        source_names=source_names,
    )
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.4,
        )
        raw = response.choices[0].message.content or ""
        parsed = parse_nex_prompts_response(raw)
        if parsed:
            return parsed
        logger.warning("Nex prompts parse failed for title=%r", title[:60])
    except Exception:
        logger.exception("Nex prompts LLM call failed for title=%r", title[:60])

    return fallback_nex_prompts(title)


def save_nex_prompts_for_cluster(
    cluster: Any,
    client: Any,
    model: str,
) -> list[str]:
    """
    Generate and persist suggested_prompts on a cluster with a non-empty summary.
    Skips if prompts already exist. Never raises.
    """
    existing = cluster.suggested_prompts if isinstance(cluster.suggested_prompts, list) else []
    if existing:
        return existing[:MAX_PROMPTS]

    article = cluster.primary_article
    if not article:
        return []

    summary = (cluster.summary or "").strip()
    if not summary:
        return []

    category_slug = ""
    if article.source and article.source.category:
        category_slug = article.source.category.slug or ""

    prompts = generate_nex_prompts_for_cluster(
        client,
        model,
        title=article.title or "",
        summary=summary,
        category_slug=category_slug,
        source_names=cluster.source_names(),
    )
    try:
        cluster.suggested_prompts = prompts
        cluster.save(update_fields=["suggested_prompts"])
    except Exception:
        logger.exception("Failed to save Nex prompts for cluster %s", cluster.pk)
        return prompts
    return prompts
