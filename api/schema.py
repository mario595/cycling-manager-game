"""OpenAPI wiring for drf-spectacular (#130).

Imported from ApiConfig.ready() so the extension below is registered before
any schema is generated. It tells the schema that GameTokenAuthentication is
an HTTP bearer scheme; without it drf-spectacular warns that it cannot
describe the class.
"""

from __future__ import annotations

from drf_spectacular.extensions import OpenApiAuthenticationExtension


class GameTokenScheme(OpenApiAuthenticationExtension):
    target_class = "api.authentication.GameTokenAuthentication"
    name = "bearerAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "description": "An API token issued by the game's operator.",
        }
