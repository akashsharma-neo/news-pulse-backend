"""NewsPulse root URL configuration — aggregates all app URL patterns.

Routes:
    /admin/          — Django admin panel
    /api/schema/     — OpenAPI schema (drf-spectacular)
    /api/docs/       — Swagger UI (drf-spectacular)
    /api/*           — REST API endpoints (articles, sources, chat, digest, users)
"""
from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path('admin/', admin.site.urls),
    # Swagger / OpenAPI
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    # API endpoints
    path('api/', include('articles.urls')),
    path('api/', include('sources.urls')),
    path('api/', include('chat.urls')),
    path('api/', include('digest.urls')),
    path('api/', include('users.urls')),
]
