from django.apps import AppConfig


class ApiConfig(AppConfig):
    name = "api"
    verbose_name = "API"

    def ready(self):
        from api import schema  # noqa: F401 — registers the OpenAPI auth extension
