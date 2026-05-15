"""Celery app configuration for NewsPulse.

Discovers tasks from all installed apps automatically via `app.autodiscover_tasks()`.
Includes a beat schedule for periodic scraping, clustering, and embedding.
"""
import os
from celery import Celery
from celery.signals import beat_init
from datetime import timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

app = Celery('core')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()

# Merge beat schedule: Django `CELERY_BEAT_SCHEDULE` is loaded above; add/override
# worker periodic tasks here so digest/settings entries are not dropped.
_beat = dict(app.conf.beat_schedule or {})
_beat.update(
    {
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
)
app.conf.beat_schedule = _beat

app.conf.timezone = 'Asia/Kolkata'


@beat_init.connect
def enqueue_startup_scrape(sender, **kwargs):
    """Run one scrape cycle when Beat starts so the feed is not empty for 30 minutes."""
    sender.app.send_task('worker.tasks.scrape_sources')
