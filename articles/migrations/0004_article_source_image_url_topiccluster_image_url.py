from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("articles", "0003_alter_article_embedding_alter_article_full_text_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="article",
            name="source_image_url",
            field=models.URLField(
                blank=True,
                default="",
                help_text="Lead image URL from the publisher (RSS media or web scrape)",
                max_length=2048,
            ),
        ),
        migrations.AddField(
            model_name="topiccluster",
            name="image_url",
            field=models.URLField(
                blank=True,
                default="",
                help_text="Display image URL (publisher lead image or tab placeholder)",
                max_length=2048,
            ),
        ),
    ]
