"""
NewsPulse Celery Flower configuration.

Flower is a real-time monitor and web admin for Celery tasks.

Usage:
    # Start Flower (requires Redis running):
    flower --broker=redis://localhost:6379/0 --port=5555

    # With auth (production):
    flower --broker=redis://localhost:6379/0 --port=5555 \
        --basic_auth=admin:password

    # Access at: http://localhost:5555

Features:
    - Real-time task monitoring (graph, table, timeline)
    - Task inspection (arguments, start time, runtime)
    - Broker management (queues, consume, add)
    - Application inspection (stats, inspect)
    - Authentication & authorization
"""

# Celery Beat schedule for scheduled tasks
from datetime import timedelta

beat_schedule = {
    'scrape-every-30-minutes': {
        'task': 'worker.tasks.scrape_sources',
        'schedule': timedelta(minutes=30),
    },
    'cluster-every-hour': {
        'task': 'worker.tasks.cluster_and_summarize',
        'schedule': timedelta(hours=1),
    },
    'embed-every-2-hours': {
        'task': 'worker.tasks.generate_embeddings_task',
        'schedule': timedelta(hours=2),
    },
    'embed-clusters-every-2-hours': {
        'task': 'worker.tasks.generate_cluster_embeddings_task',
        'schedule': timedelta(hours=2),
    },
}

# Flower options
flower_options = {
    'port': 5555,
    'broker_api': 'redis://localhost:6379/0',
    'basic_auth': '',  # Set 'user:password' for auth
    'persist': False,  # Don't persist state to disk
    'state_path': '',
}
