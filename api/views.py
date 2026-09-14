from __future__ import annotations

from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from racing.models import SQUAD_SIZE, Race
from racing.services import SquadError, set_squad, suggested_squad
from riders.models import ENGINE_ATTRIBUTES
from schedule.services import current_position
from teams.models import Team
from world.services import now

from .serializers import (
    CalendarSerializer,
    ClockSerializer,
    MeSerializer,
    PositionSerializer,
    SquadSerializer,
    SquadWriteSerializer,
)


def team_for(user):
    """The user's team, or None. `Team.manager` is a OneToOneField, so the
    reverse accessor raises rather than returning None when the user
    manages nothing — see specs/player-accounts-plan.md, D5. Deliberately
    not `getattr(user, "team", None)`: RelatedObjectDoesNotExist also
    subclasses AttributeError, so that spelling would silently swallow a
    genuine bug (a typo, a renamed relation) as well as the real case."""
    if not user.is_authenticated:
        return None
    try:
        return user.team
    except Team.DoesNotExist:
        return None


class ClockView(APIView):
    """The game's current time. Public by design: world data is meant to be
    visible before signup, the game's shop window. Overrides the
    project-wide IsAuthenticated default."""

    permission_classes = [AllowAny]

    def get(self, request):
        return Response(ClockSerializer({"current": now()}).data)


class PositionView(APIView):
    """Where the world is in its season: in_season, off_season, or
    no_season — see schedule/README.md. Public, for the same reason as
    ClockView."""

    permission_classes = [AllowAny]

    def get(self, request):
        position = current_position(now())
        return Response(PositionSerializer({
            "state": position.state,
            "season": position.season.number if position.season else None,
            "week": position.week.number if position.week else None,
            "week_ends_at": position.week.ends_at if position.week else None,
        }).data)


def _distance_km(race) -> float:
    return sum(s["length"] for s in race.course) / 1000


def _race_payload(race) -> dict:
    return {
        "id": race.pk,
        "name": race.name,
        "starts_at": race.starts_at,
        "status": race.status,
        "distance_km": _distance_km(race),
    }


def _week_payload(week) -> dict:
    return {
        "number": week.number,
        "starts_at": week.starts_at,
        "races": [_race_payload(r) for r in sorted(week.races.all(), key=lambda r: r.starts_at)],
    }


class CalendarView(APIView):
    """The current season's whole calendar: all twelve weeks, each with the
    race(s) on it — see schedule/README.md, *The race calendar*. Public,
    for the same reason as ClockView."""

    permission_classes = [AllowAny]

    def get(self, request):
        position = current_position(now())
        if position.season is None or position.state != "in_season":
            return Response(CalendarSerializer({
                "state": position.state,
                "season": position.season.number if position.season else None,
                "current_week": None,
                "weeks": [],
            }).data)

        weeks = position.season.weeks.prefetch_related("races").order_by("number")
        return Response(CalendarSerializer({
            "state": position.state,
            "season": position.season.number,
            "current_week": position.week.number if position.week else None,
            "weeks": [_week_payload(w) for w in weeks],
        }).data)


class MeView(APIView):
    """Who is logged in, if anyone, and what team they manage, if any. One
    request answers both, so the SPA does not need a second round trip on
    boot to learn its own team.

    Public — an anonymous visitor is a valid answer, not an error. The
    ensure_csrf_cookie decorator is load-bearing: this is the request that
    guarantees the SPA holds a CSRF token before it ever issues a write —
    see specs/player-accounts-plan.md, D4."""

    permission_classes = [AllowAny]

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        user = request.user
        team = team_for(user)
        payload = {
            "authenticated": user.is_authenticated,
            "display_name": user.display_name if user.is_authenticated else None,
            "team": {"id": team.pk, "name": team.name, "code": team.code} if team else None,
        }
        return Response(MeSerializer(payload).data)


def _squad_payload(race, team, rider_ids: list[int], leader_id: int, *, saved: bool) -> dict:
    selected = set(rider_ids)
    candidates = [
        {
            "id": rider.pk,
            "name": rider.name,
            "role": rider.role,
            **{name: getattr(rider, name) for name in ENGINE_ATTRIBUTES},
            "selected": rider.pk in selected,
            "is_leader": rider.pk == leader_id,
        }
        for rider in team.riders.all().order_by("name")
    ]
    return {
        "race": race.pk,
        "race_name": race.name,
        "race_status": race.status,
        "starts_at": race.starts_at,
        "distance_km": _distance_km(race),
        "team": team.pk,
        "team_name": team.name,
        "editable": race.status == Race.Status.SCHEDULED,
        "saved": saved,
        "squad_size": len(rider_ids),
        "candidates": candidates,
    }


class SquadView(APIView):
    """The caller's own team's squad for one race — read it, replace it.

    No team id in the URL: the team is always the caller's own, from
    request.user via team_for(). Falls back to the project default,
    IsAuthenticated — do not re-add AllowAny. See
    specs/player-accounts-plan.md, D8.
    """

    def get(self, request, race_id: int):
        race = get_object_or_404(Race, pk=race_id)
        team = team_for(request.user)
        if team is None:
            return Response({"detail": "You do not manage a team."}, status=403)

        existing = race.squads.filter(team=team).prefetch_related("members").first()
        saved_selection = None
        if existing is not None:
            members = list(existing.members.all())
            leader_id = next((m.rider_id for m in members if m.is_leader), None)
            if len(members) == SQUAD_SIZE and leader_id is not None:
                saved_selection = ([m.rider_id for m in members], leader_id)

        if saved_selection is not None:
            rider_ids, leader_id = saved_selection
            saved = True
        else:
            rider_ids, leader_id = suggested_squad(race, team)
            saved = False

        payload = _squad_payload(race, team, rider_ids, leader_id, saved=saved)
        return Response(SquadSerializer(payload).data)

    def put(self, request, race_id: int):
        race = get_object_or_404(Race, pk=race_id)
        team = team_for(request.user)
        if team is None:
            return Response({"detail": "You do not manage a team."}, status=403)

        write = SquadWriteSerializer(data=request.data)
        write.is_valid(raise_exception=True)

        try:
            set_squad(race, team, write.validated_data["rider_ids"], write.validated_data["leader_id"])
        except SquadError as exc:
            return Response({"detail": str(exc)}, status=400)

        payload = _squad_payload(
            race, team, write.validated_data["rider_ids"], write.validated_data["leader_id"], saved=True,
        )
        return Response(SquadSerializer(payload).data)
