from __future__ import annotations

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from world.services import now

from .serializers import ClockSerializer


class ClockView(APIView):
    """The game's current time. Public: the date is not private, and there
    is no login flow in the SPA yet — an authenticated endpoint would
    render the feature invisible. Overrides the project-wide IsAuthenticated
    default."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response(ClockSerializer({"current": now()}).data)
