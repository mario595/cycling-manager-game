"""`GET /healthz`, answered before the rest of the middleware stack.

Fly's health checks reach the machine over plain HTTP on its internal
address, with a Host header that is not in `ALLOWED_HOSTS`. A normal view
would be redirected to HTTPS by `SecurityMiddleware` (prod's
`SECURE_SSL_REDIRECT`) or rejected by host validation before it ran, so this
lives as the first middleware and never calls `request.get_host()`.

It checks the one dependency that can be down while gunicorn is up: the
database. 200 `ok` when a trivial query works, 503 otherwise. See
`deploy/README.md`.
"""

from __future__ import annotations

from django.db import connection
from django.http import HttpResponse

HEALTH_PATH = "/healthz"


class HealthCheckMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path_info != HEALTH_PATH:
            return self.get_response(request)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
        except Exception:  # noqa: BLE001 - any database failure is "unhealthy"
            return HttpResponse("database unavailable", status=503, content_type="text/plain")
        return HttpResponse("ok", content_type="text/plain")
