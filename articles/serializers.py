"""
NewsPulse REST serializers.

Maps models to JSON for API responses. Uses nested read-only fields
for related objects (source name, category slug, etc.).
"""

from rest_framework import serializers

from articles.image_resolver import resolve_cluster_display_image
from worker.article_content import clean_article_text, truncate_at_sentence_boundary

from .models import Tab, Source, Article, TopicCluster


class TabSerializer(serializers.ModelSerializer):
    """Serialize a Tab (news category) for API responses."""

    class Meta:
        model = Tab
        fields = ["id", "name", "slug", "order"]
        read_only_fields = fields


class SourceSerializer(serializers.ModelSerializer):
    """Serialize a Source (news outlet) for API responses."""

    class Meta:
        model = Source
        fields = ["id", "name", "url", "category", "source_type", "active"]
        read_only_fields = ["id", "created_at", "updated_at"]


class ArticleSerializer(serializers.ModelSerializer):
    """Serialize an Article with denormalized source/category info.

    Extra fields:
        source_name: Human-readable name of the source (e.g. 'BBC').
        category_slug: Tab slug (e.g. 'india', 'sports').
    """

    source_name = serializers.CharField(
        source="source.name",
        read_only=True,
        help_text="Name of the news source",
    )
    category_slug = serializers.CharField(
        source="source.category.slug",
        read_only=True,
        help_text="Tab slug this article belongs to",
    )

    class Meta:
        model = Article
        fields = [
            "id", "title", "url", "source_name", "category_slug",
            "published_at", "summary", "source_image_url",
        ]
        read_only_fields = fields


class TopicClusterSerializer(serializers.ModelSerializer):
    """Serialize a TopicCluster with denormalized article + source info.

    A TopicCluster groups multiple articles covering the same story.
    This serializer flattens the most important fields for feed display.

    Extra fields:
        primary_title: Title of the representative article.
        primary_url: URL of the representative article.
        source_name: Name of the primary article's source.
        category_slug: Tab slug.
        published_at: Published time of the primary article.
        source_names: List of all source names in the cluster.
        summary: AI digest, or a short excerpt from the primary article when
            summarization has not completed yet.
    """

    summary = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()

    primary_title = serializers.CharField(
        source="primary_article.title",
        read_only=True,
    )
    primary_url = serializers.CharField(
        source="primary_article.url",
        read_only=True,
    )
    source_name = serializers.CharField(
        source="primary_article.source.name",
        read_only=True,
    )
    category_slug = serializers.CharField(
        source="primary_article.source.category.slug",
        read_only=True,
    )
    published_at = serializers.DateTimeField(
        source="primary_article.published_at",
        read_only=True,
    )
    source_names = serializers.SerializerMethodField(
        help_text="List of all source names contributing to this cluster",
    )

    class Meta:
        model = TopicCluster
        fields = [
            "id", "topic_id", "primary_title", "primary_url",
            "source_name", "category_slug", "published_at",
            "summary", "source_names", "image_url", "created_at",
        ]
        read_only_fields = fields

    def get_image_url(self, obj: TopicCluster) -> str:
        """Resolved display image: cluster field, primary article, or placeholder."""
        return resolve_cluster_display_image(obj)

    def get_source_names(self, obj: TopicCluster) -> list[str]:
        """Return the list of source names in this cluster."""
        return obj.source_names()

    def get_summary(self, obj: TopicCluster) -> str:
        """LLM digest when present; otherwise a cleaned excerpt from the primary article."""
        if obj.summary:
            return clean_article_text(obj.summary)
        article = obj.primary_article
        if not article:
            return ""
        if article.summary:
            return clean_article_text(article.summary)
        text = clean_article_text(article.full_text or "")
        if text:
            return truncate_at_sentence_boundary(text)
        return article.title or ""
