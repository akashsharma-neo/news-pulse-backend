"""Lightweight health check (HTTP, no auth) for load balancers and orchestrators."""

from django.http import JsonResponse


def health(request):
    return JsonResponse({"status": "ok"})
