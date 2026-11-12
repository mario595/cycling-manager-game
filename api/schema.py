"""OpenAPI wiring for drf-spectacular (#130).

Imported from ApiConfig.ready() so the extension below is registered before
any schema is generated. It tells the schema that GameTokenAuthentication is
an HTTP bearer scheme; without it drf-spectacular warns that it cannot
describe the class.
"""

from __future__ import annotations

from drf_spectacular.extensions import OpenApiAuthenticationExtension
from drf_spectacular.utils import OpenApiResponse
from rest_framework import serializers


class GameTokenScheme(OpenApiAuthenticationExtension):
    target_class = "api.authentication.GameTokenAuthentication"
    name = "bearerAuth"

    def get_security_definition(self, auto_schema):
        return {
            "type": "http",
            "scheme": "bearer",
            "description": "An API token issued by the game's operator.",
        }


# --- Shared pieces for the @extend_schema decorators in api/views.py ---------


class DetailSerializer(serializers.Serializer):
    """The body of every refusal: one human-readable sentence."""

    detail = serializers.CharField()


NO_TEAM = "You do not manage a team. Claim one first (`POST /api/teams/claim/`)."


def refused(**codes: str) -> dict:
    """`refused(r403=..., r409=...)` → responses for each refusal, each a
    `{"detail": ...}` body with the given game-terms explanation."""
    return {
        int(code[1:]): OpenApiResponse(response=DetailSerializer, description=text)
        for code, text in codes.items()
    }


def pct(rate: float) -> int:
    """A fee rate as a whole percentage, for descriptions."""
    return round(rate * 100)
