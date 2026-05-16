"""NewsPulse root URL configuration — aggregates all app URL patterns.

Routes:
    /admin/          — Django admin panel
    /api/schema/     — OpenAPI schema (drf-spectacular)
    /api/docs/       — Swagger UI (drf-spectacular)
    /api/*           — REST API endpoints (articles, sources, chat, digest, users)
"""
from django.conf import settings
from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from core.health import health

urlpatterns = [
    path('health/', health, name='health'),
    path('admin/', admin.site.urls),
]

if settings.ENABLE_API_DOCS:
    urlpatterns += [
        path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
        path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    ]

urlpatterns += [
    path('api/', include('articles.urls')),
    path('api/', include('sources.urls')),
    path('api/', include('chat.urls')),
    path('api/', include('digest.urls')),
    path('api/', include('users.urls')),
]
