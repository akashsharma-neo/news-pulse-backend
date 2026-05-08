"""ASGI entry-point for NewsPulse.

Used by asgi-compatible servers (Uvicorn, Daphne) for WebSocket/HTTP2.
"""
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
application = get_asgi_application()
