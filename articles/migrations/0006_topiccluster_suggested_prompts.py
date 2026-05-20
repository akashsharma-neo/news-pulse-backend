from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("articles", "0005_article_topic_cluster"),
    ]

    operations = [
        migrations.AddField(
            model_name="topiccluster",
            name="suggested_prompts",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Up to 3 short tap-to-ask questions for Nex chat",
            ),
        ),
    ]
