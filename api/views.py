from __future__ import annotations

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from schedule.services import current_position
from world.services import now

from .serializers import ClockSerializer, PositionSerializer


class ClockView(APIView):
    """The game's current time. Public: the date is not private, and there
    is no login flow in the SPA yet — an authenticated endpoint would
    render the feature invisible. Overrides the project-wide IsAuthenticated
    default."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response(ClockSerializer({"current": now()}).data)


class PositionView(APIView):
    """Where the world is in its season: in_season, off_season, or
    no_season — see schedule/README.md. Public, for the same reason
    ClockView is."""

    permission_classes = [AllowAny]

    def get(self, request):
        position = current_position(now())
        return Response(PositionSerializer({
            "state": position.state,
            "season": position.season.number if position.season else None,
            "week": position.week.number if position.week else None,
            "week_ends_at": position.week.ends_at if position.week else None,
        }).data)
