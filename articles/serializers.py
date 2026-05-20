"""
NewsPulse REST serializers.

Maps models to JSON for API responses. Uses nested read-only fields
for related objects (source name, category slug, etc.).
"""

from rest_framework import serializers

from articles.image_resolver import resolve_cluster_display_image
from worker.article_content import clean_article_text, truncate_at_sentence_boundary

from .models import Tab, Source, Article, TopicCluster


class SearchResultSerializer(serializers.Serializer):
    """Serialize an Article for search results with highlighted snippet."""

    id = serializers.IntegerField()
    title = serializers.CharField()
    url = serializers.URLField()
    source_name = serializers.CharField(source="source.name")
    category_slug = serializers.CharField(source="source.category.slug")
    published_at = serializers.DateTimeField()
    summary = serializers.CharField()
    source_image_url = serializers.URLField()
    headline = serializers.CharField(read_only=True, default="")


class SuggestionSerializer(serializers.Serializer):
    """Serialize a search suggestion (keyword or title)."""

    text = serializers.CharField(help_text="Suggested search text")
    type = serializers.ChoiceField(
        choices=["keyword", "title"],
        help_text="Whether this is a keyword or article title suggestion",
    )


class TrendingSerializer(serializers.Serializer):
    """Serialize a trending topic."""

    text = serializers.CharField(help_text="Trending topic name or label")
    type = serializers.ChoiceField(
        choices=["tab", "cluster"],
        help_text="Type of trending item: tab (browse category) or cluster (popular story)",
    )
    slug = serializers.CharField(
        help_text="Tab slug for tab type, or empty for cluster",
        required=False,
        default="",
    )
    cluster_id = serializers.IntegerField(
        help_text="Cluster ID for cluster type, or null",
        required=False,
        default=None,
    )


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
    suggested_prompts = serializers.ListField(
        child=serializers.CharField(max_length=120),
        read_only=True,
        help_text="Up to 3 Nex tap-to-ask questions for this story",
    )

    class Meta:
        model = TopicCluster
        fields = [
            "id", "topic_id", "primary_title", "primary_url",
            "source_name", "category_slug", "published_at",
            "summary", "source_names", "image_url", "suggested_prompts",
            "created_at",
        ]
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        prompts = instance.suggested_prompts if isinstance(instance.suggested_prompts, list) else []
        data["suggested_prompts"] = [
            str(p).strip() for p in prompts[:3] if p and str(p).strip()
        ]
        return data

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
