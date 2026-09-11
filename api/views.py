from __future__ import annotations

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from world.models import GameClock

from .serializers import GameClockSerializer


class ClockView(APIView):
    """The world's current game time. Public: the date is not private, and
    there is no login flow in the SPA yet — an authenticated endpoint would
    render the feature invisible. Overrides the project-wide IsAuthenticated
    default."""

    permission_classes = [AllowAny]

    def get(self, request):
        clock = GameClock.load()
        return Response(GameClockSerializer(clock).data)
