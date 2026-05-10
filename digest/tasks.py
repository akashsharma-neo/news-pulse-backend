"""
NewsPulse digest Celery tasks.

Tasks:
    generate_daily_digest_task — Picks top stories for today, builds an
        AI-curated summary, and emails all active subscribers.
"""

import logging
from datetime import timedelta

from celery import shared_task
from celery.utils.log import get_task_logger
from django.utils import timezone as dj_timezone
from django.core.mail import send_mail
from django.conf import settings

from articles.models import TopicCluster, Tab
from digest.models import EmailSubscriber

logger = get_task_logger(__name__)


def _get_top_stories(tabs=None, limit=10):
    """Return the most recent TopicClusters, optionally filtered by tabs.

    Only includes clusters from the last 24 hours.
    """
    cutoff = dj_timezone.now() - timedelta(hours=24)
    qs = TopicCluster.objects.filter(
        created_at__gte=cutoff,
        primary_article__published_at__gte=cutoff,
    ).select_related("primary_article").order_by("-created_at")

    if tabs:
        qs = qs.filter(
            primary_article__source__category__slug__in=tabs
        ).distinct()

    return list(qs[:limit])


def _build_digest_html(stories, tabs=None):
    """Build an HTML email body from a list of TopicClusters.

    Returns a dict with 'subject', 'body_text', and 'body_html'.
    """
    tab_label = "all topics" if not tabs else ", ".join(tabs)
    subject = f"NewsPulse Daily Digest — {tab_label} ({len(stories)} stories)"

    lines = [
        "<html>",
        "<body style='font-family: -apple-system, BlinkMacSystemFont, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;'>",
        "<h1 style='color: #1a1a2e;'>NewsPulse Daily Digest</h1>",
        f"<p style='color: #666;'>Top stories from {tab_label} — {len(stories)} stories today.</p>",
        "<hr style='border: none; border-top: 1px solid #eee; margin: 20px 0;'>",
    ]

    for i, cluster in enumerate(stories, 1):
        lines.append(f"<div style='margin-bottom: 24px;'>")
        lines.append(f"<span style='color: #888; font-size: 12px;'>#{i}</span>")
        lines.append(f"<h2 style='margin: 4px 0 8px;'><a href='{cluster.primary_article.url}' style='color: #1a1a2e; text-decoration: none;'>{cluster.primary_article.title}</a></h2>")
        lines.append(f"<p style='color: #444; line-height: 1.6; margin: 0 0 8px;'>{cluster.summary}</p>")
        if cluster.sources:
            lines.append(f"<p style='color: #888; font-size: 12px; margin: 0;'>Sources: {', '.join(cluster.sources)}</p>")
        lines.append("</div>")

    lines.extend([
        "<hr style='border: none; border-top: 1px solid #eee; margin: 20px 0;'>",
        f"<p style='color: #aaa; font-size: 12px;'>You're receiving this because you subscribed to NewsPulse Digest.</p>",
        "</body>",
        "</html>",
    ])

    body_html = "\n".join(lines)
    body_text = f"{subject}\n\n" + "\n\n".join(
        f"{i}. {c.primary_article.title}\n   {c.summary}\n   Sources: {', '.join(c.sources)}\n   {c.primary_article.url}"
        for i, c in enumerate(stories, 1)
    )

    return subject, body_text, body_html


@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def generate_daily_digest_task(self):
    """
    Generate and send the daily digest to all active subscribers.

    1. Fetch top stories from the last 24 hours (per subscriber's tab preferences).
    2. Build an HTML email for each subscriber.
    3. Send via Django's SMTP backend.

    Returns {"sent": N, "failed": N, "total_subscribers": N}.
    """
    try:
        active_subscribers = list(
            EmailSubscriber.objects.filter(is_active=True).values_list("id", "email", "tabs")
        )

        if not active_subscribers:
            logger.info("No active subscribers — digest skipped")
            return {"sent": 0, "failed": 0, "total_subscribers": 0}

        total_sent = 0
        total_failed = 0

        for sub_id, email, tabs in active_subscribers:
            try:
                stories = _get_top_stories(tabs=tabs, limit=10)
                if not stories:
                    logger.info("No stories for subscriber %s — skipping", email)
                    total_sent += 1  # still counts as "sent" (empty digest is fine)
                    continue

                subject, body_text, body_html = _build_digest_html(stories, tabs)

                send_mail(
                    subject=subject,
                    message=body_text,
                    html_message=body_html,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    fail_silently=False,
                )

                total_sent += 1
                logger.info("Digest sent to %s (%d stories)", email, len(stories))

            except Exception as e:
                total_failed += 1
                logger.error("Failed to send digest to %s: %s", email, e, exc_info=True)

        return {"sent": total_sent, "failed": total_failed, "total_subscribers": len(active_subscribers)}

    except Exception as e:
        logger.error("Digest generation failed: %s", e, exc_info=True)
        raise self.retry(exc=e)
