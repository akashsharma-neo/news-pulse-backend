"""
NewsPulse article domain models.

Defines Tab, Source, Article, and TopicCluster — the core data structures
that power the news aggregation, clustering, and feed pipeline.
"""

from django.db import models
from django.utils import timezone
from pgvector.django import VectorField


class Tab(models.Model):
    """News category tabs displayed in the navigation bar.

    Examples: India, Sports, Business, Global, Just For You.
    Each tab groups sources and articles by topic.
    """

    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Human-readable tab name, e.g. 'India'",
    )
    slug = models.SlugField(
        max_length=50,
        unique=True,
        help_text="URL-safe slug, e.g. 'india'",
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Display order in the tab bar (lower = leftmost)",
    )

    class Meta:
        ordering = ["order"]

    def __str__(self) -> str:
        return self.name


class Source(models.Model):
    """A news source — where articles are fetched from.

    Supports three ingestion methods:
    - **web**: HTML page scraped with BeautifulSoup
    - **rss**: RSS/Atom feed parsed with feedparser
    - **api**: External API endpoint
    """

    SOURCE_TYPES = (
        ("web", "Web Scraper"),
        ("rss", "RSS Feed"),
        ("api", "API"),
    )

    name = models.CharField(
        max_length=200,
        help_text="Source name, e.g. 'NDTV', 'BBC News'",
    )
    url = models.URLField(
        help_text="Base URL or RSS feed URL for this source",
    )
    category = models.ForeignKey(
        Tab,
        on_delete=models.CASCADE,
        related_name="sources",
        help_text="Which tab this source belongs to",
    )
    source_type = models.CharField(
        max_length=20,
        choices=SOURCE_TYPES,
        default="web",
    )
    active = models.BooleanField(
        default=True,
        help_text="Whether this source should be scraped",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.category.name})"


class Article(models.Model):
    """A single news article fetched from a Source.

    Stores the raw article data (title, URL, full text) plus an optional
    embedding vector for similarity-based clustering.
    """

    title = models.CharField(
        max_length=1000,
        help_text="Headline of the article",
    )
    url = models.URLField(
        max_length=2048,
        help_text="Canonical URL of the original article",
    )
    source = models.ForeignKey(
        Source,
        on_delete=models.CASCADE,
        related_name="articles",
    )
    published_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Original publication time from the source",
    )
    full_text = models.TextField(
        blank=True,
        default="",
        help_text="Full article body (truncated to ~2000 chars by scraper)",
    )
    fetched_at = models.DateTimeField(auto_now_add=True)
    summary = models.TextField(
        blank=True,
        default="",
        help_text="AI-generated one-line summary",
    )
    embedding = VectorField(
        dimensions=768,
        blank=True,
        null=True,
        help_text="768-dim embedding vector for similarity search",
    )

    class Meta:
        ordering = ["-published_at"]
        indexes = [
            models.Index(fields=["-published_at"]),
            models.Index(fields=["source", "-published_at"]),
        ]

    def __str__(self) -> str:
        return self.title[:100]


class TopicCluster(models.Model):
    """A group of articles covering the same story from different sources.

    Created automatically by the clustering pipeline (task 1.5). Each cluster
    has one primary article and an AI-generated unified summary that combines
    perspectives from all sources in the cluster.
    """

    topic_id = models.UUIDField(
        help_text="AI-generated unique ID for the story cluster",
    )
    primary_article = models.ForeignKey(
        Article,
        on_delete=models.CASCADE,
        related_name="clustered_as_primary",
        help_text="The newest/most representative article in this cluster",
    )
    summary = models.TextField(
        help_text="AI-generated unified summary (~60-80 words, InShorts style)",
    )
    sources = models.JSONField(
        default=list,
        blank=True,
        help_text="List of source names contributing to this cluster",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["topic_id"]),
        ]

    def __str__(self) -> str:
        return self.primary_article.title[:100]

    def source_names(self) -> list[str]:
        """Return the list of source names in this cluster.

        Returns:
            List of source name strings, or empty list if sources is not a list.
        """
        return self.sources if isinstance(self.sources, list) else []
