from django.db import migrations
from django.contrib.postgres.operations import TrigramExtension


class Migration(migrations.Migration):

    dependencies = [
        ("articles", "0007_topiccluster_keywords"),
    ]

    operations = [
        TrigramExtension(),
        migrations.RunSQL(
            sql="""
            CREATE INDEX IF NOT EXISTS idx_topiccluster_keywords_trgm
            ON articles_topiccluster
            USING gin ((keywords::text) gin_trgm_ops);
            """,
            reverse_sql="""
            DROP INDEX IF EXISTS idx_topiccluster_keywords_trgm;
            """,
        ),
        migrations.RunSQL(
            sql="""
            CREATE INDEX IF NOT EXISTS idx_article_full_text_trgm
            ON articles_article
            USING gin (full_text gin_trgm_ops);
            """,
            reverse_sql="""
            DROP INDEX IF EXISTS idx_article_full_text_trgm;
            """,
        ),
    ]
