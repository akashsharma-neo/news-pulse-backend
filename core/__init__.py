"""NewsPulse core package — Django project configuration.

Exports:
    celery_app: Celery application instance (auto-discovered tasks).
"""
from .celery import app as celery_app

__all__ = ('celery_app',)
