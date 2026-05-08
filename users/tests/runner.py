import sys
from pathlib import Path

# Add the project root to sys.path so that imports like 'core', 'articles' work correctly
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(project_root))

from django.test.runner import DiscoverRunner
from django.db import connection, transaction


class NewsPulseTestRunner(DiscoverRunner):
    """Test runner that enables pgvector on the test database."""

    def setup_databases(self, **kwargs):
        # Patch call_command to enable pgvector before migrate
        from django.core.management import call_command as original_call_command

        def patched_call_command(name, *args, **kwargs):
            if name == "migrate":
                with transaction.atomic():
                    with connection.cursor() as cur:
                        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            return original_call_command(name, *args, **kwargs)

        import django.core.management
        django.core.management.call_command = patched_call_command

        try:
            return super().setup_databases(**kwargs)
        finally:
            django.core.management.call_command = original_call_command
