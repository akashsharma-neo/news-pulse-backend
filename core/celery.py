"""Celery app configuration for NewsPulse.

Discovers tasks from all installed apps automatically via `app.autodiscover_tasks()`.
Includes a beat schedule for periodic scraping, clustering, and embedding.
"""
import os
from celery import Celery
from datetime import timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

app = Celery('core')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Celery Beat schedule — scheduled background tasks
app.conf.beat_schedule = {
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

app.conf.timezone = 'Asia/Kolkata'
