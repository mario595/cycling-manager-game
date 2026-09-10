"""Root URL configuration.

Layout: Django owns `/admin/` and `/api/`; everything else falls through to
the React single-page app, which does its own client-side routing. The
catch-all must therefore stay last.
"""

from __future__ import annotations

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path
from django.views.generic import TemplateView

urlpatterns = [
    path("admin/", admin.site.urls),
    # Per-app API routes get included here as they are built:
    #   path("api/", include("api.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# SPA catch-all. Serves the built React bundle for any non-API path so that
# deep links and browser refreshes work. Keep this last.
urlpatterns += [
    path("", TemplateView.as_view(template_name="index.html"), name="spa"),
    path("<path:unused>", TemplateView.as_view(template_name="index.html")),
]
