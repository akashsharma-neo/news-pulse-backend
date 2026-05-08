"""
NewsPulse source domain model.

Defines ScraperConfig — per-source configuration for web scrapers
(CSS selectors, headers, delays).
"""

from django.db import models


class ScraperConfig(models.Model):
    """Configuration for a news scraper source.

    Stores CSS selectors and request settings for web-scraped sources.
    RSS/API sources do not need this configuration.

    Fields:
        selector_title: CSS selector for the article title element.
        selector_content: CSS selector for the article content element.
        selector_date: CSS selector for the publication date element.
        custom_headers: Optional HTTP headers to send with requests.
        delay_min: Minimum delay (seconds) between requests to same domain.
        delay_max: Maximum delay (seconds) between requests.
        enabled: Whether scraping is active for this source.
    """

    source = models.OneToOneField(
        "articles.Source",
        on_delete=models.CASCADE,
        related_name="scraper_config",
    )
    selector_title = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="CSS selector for the title element (e.g. 'h1, .story-title')",
    )
    selector_content = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="CSS selector for the content element (e.g. 'article, .story-body')",
    )
    selector_date = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="CSS selector for the date element",
    )
    custom_headers = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional HTTP headers for the scraper",
    )
    delay_min = models.FloatField(
        default=1.0,
        help_text="Minimum delay in seconds between requests",
    )
    delay_max = models.FloatField(
        default=2.0,
        help_text="Maximum delay in seconds between requests",
    )
    enabled = models.BooleanField(
        default=True,
        help_text="Whether this scraper is active",
    )

    def __str__(self) -> str:
        return f"Scraper: {self.source.name}"
