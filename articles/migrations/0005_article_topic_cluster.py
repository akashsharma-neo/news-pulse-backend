"""Add topic_cluster FK on Article for persisted cluster membership."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("articles", "0004_article_source_image_url_topiccluster_image_url"),
    ]

    operations = [
        migrations.AddField(
            model_name="article",
            name="topic_cluster",
            field=models.ForeignKey(
                blank=True,
                help_text="Story cluster this article belongs to (set by clustering pipeline)",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="member_articles",
                to="articles.topiccluster",
            ),
        ),
    ]
