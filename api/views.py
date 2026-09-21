from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db.models import Sum
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from competitions.scoring import POINTS_BY_POSITION, points_for, prize_for
from competitions.services import standings
from economy.models import LedgerEntry
from economy.services import balance_for, entries_for
from racing.models import SQUAD_SIZE, Race
from racing.services import SquadError, set_squad, suggested_squad
from riders.models import ENGINE_ATTRIBUTES, Rider
from schedule.services import current_position
from staff.services import (
    NoTrainerHired,
    SlotOccupied,
    TrainerNotAvailable,
    available_trainers,
    fire_trainer,
    focus_for,
    hire_trainer,
    latest_report,
    set_focus,
    trainer_for,
)
from teams.models import Team
from teams.services import NoTeamAvailable, claim_team
from world.services import now

from .serializers import (
    CalendarSerializer,
    ClaimTeamSerializer,
    ClockSerializer,
    FinancesSerializer,
    HireTrainerSerializer,
    MeSerializer,
    MeTeamSerializer,
    PositionSerializer,
    RaceDetailSerializer,
    RaceResultsSerializer,
    RiderSerializer,
    SquadSerializer,
    SquadWriteSerializer,
    StaffSerializer,
    StandingsSerializer,
    TrainingFocusSerializer,
    TrainingSerializer,
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
    """The game's current time. Requires a session: the game exposes nothing
    to a visitor who is not logged in — see api/README.md, *Authentication*."""

    def get(self, request):
        return Response(ClockSerializer({"current": now()}).data)


class PositionView(APIView):
    """Where the world is in its season: in_season, off_season, or
    no_season — see schedule/README.md. Requires a session: the game
    exposes nothing to a visitor who is not logged in — see api/README.md,
    *Authentication*."""

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
    race(s) on it — see schedule/README.md, *The race calendar*. Requires a
    session: the game exposes nothing to a visitor who is not logged in —
    see api/README.md, *Authentication*."""

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
            "speciality": rider.get_speciality_display(),
            "age": rider.age,
            "freshness": rider.freshness,
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


class ClaimTeamView(APIView):
    """Assign the caller an unmanaged team, renamed and recoded to their
    choosing, with a fresh roster. Falls back to the project default,
    IsAuthenticated — do not re-add AllowAny.

    409 for both "already managing" and "no team available": the request is
    well-formed, but the world's state refuses it. 400 is reserved for a
    malformed name or code.
    """

    def post(self, request):
        if team_for(request.user) is not None:
            return Response({"detail": "You already manage a team."}, status=409)

        serializer = ClaimTeamSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            team = claim_team(
                request.user,
                name=serializer.validated_data["name"],
                code=serializer.validated_data["code"],
                at=now(),
            )
        except NoTeamAvailable as exc:
            return Response({"detail": str(exc)}, status=409)
        except DjangoValidationError as exc:
            return Response({"detail": exc.messages[0]}, status=400)
        except IntegrityError:
            return Response({"detail": "That team name is already taken."}, status=400)

        return Response(
            MeTeamSerializer({"id": team.pk, "name": team.name, "code": team.code}).data,
            status=201,
        )


class RiderListView(APIView):
    """The caller's own team's roster.

    No team id in the URL: the team is always the caller's own, from
    request.user via team_for() — same pattern as SquadView, added after
    #50 closed the anyone-can-view-anyone's-roster hole this endpoint
    would otherwise have. Falls back to the project default,
    IsAuthenticated — do not re-add AllowAny.
    """

    def get(self, request):
        team = team_for(request.user)
        if team is None:
            return Response({"detail": "You do not manage a team."}, status=403)

        riders = Rider.objects.filter(team=team)
        return Response(RiderSerializer(riders, many=True).data)


class RaceDetailView(APIView):
    """One race's own facts — identity, status, when, how far, and the
    course profile. Unlike SquadView this is not about the caller's team:
    any authenticated manager may read any race, including one their team
    did not start. See specs/race-detail-view-plan.md, D1."""

    def get(self, request, race_id: int):
        race = get_object_or_404(Race, pk=race_id)
        payload = {
            "id": race.pk,
            "name": race.name,
            "status": race.status,
            "starts_at": race.starts_at,
            "distance_km": _distance_km(race),
            "course": race.course,
            "payout": [
                {"position": p, "points": points_for(p), "prize": prize_for(p)}
                for p in sorted(POINTS_BY_POSITION)
            ],
        }
        return Response(RaceDetailSerializer(payload).data)


class RaceResultsView(APIView):
    """A finished race's order, plus each team's points from it.

    A race that has not reached FINISHED has no results to show — a 404,
    not a 200 with an empty list, so the SPA cannot mistake "not run yet"
    for "nobody scored". See competitions/README.md for what a team's
    points are computed from.
    """

    def get(self, request, race_id: int):
        race = get_object_or_404(Race, pk=race_id)
        if race.status != Race.Status.FINISHED:
            raise Http404("race has not finished")

        results = race.results.select_related("rider__team").order_by("position")
        points = race.points.select_related("team").order_by("position")
        scored = {p.team_id: p for p in points}
        starters = (
            Team.objects
            .filter(race_squads__race=race)
            .distinct()
            .order_by("name")
        )
        prizes = (
            LedgerEntry.objects
            .filter(race=race, kind=LedgerEntry.Kind.PRIZE_MONEY)
            .values("team_id")
            .annotate(total=Sum("amount"))
        )
        prize_by_team = {p["team_id"]: p["total"] for p in prizes}
        points_payload = [
            {
                "team": {"id": p.team.pk, "name": p.team.name, "code": p.team.code},
                "position": p.position,
                "points": p.points,
                "prize": prize_by_team.get(p.team_id, 0),
            }
            for p in points
        ] + [
            {
                "team": {"id": t.pk, "name": t.name, "code": t.code},
                "position": None,
                "points": 0,
                "prize": prize_by_team.get(t.pk, 0),
            }
            for t in starters
            if t.pk not in scored
        ]

        payload = {
            "race": {"id": race.pk, "name": race.name, "status": race.status},
            "results": [
                {
                    "position": r.position,
                    "rider": {"id": r.rider.pk, "name": r.rider.name},
                    "team": {
                        "id": r.rider.team.pk, "name": r.rider.team.name, "code": r.rider.team.code,
                    } if r.rider.team_id else None,
                    "finish_time": r.finish_time,
                    "finished": r.finish_time is not None,
                }
                for r in results
            ],
            "points": points_payload,
        }
        return Response(RaceResultsSerializer(payload).data)


class StandingsView(APIView):
    """The current season's standings table — see competitions/README.md
    for how points accumulate and how ties are broken.

    Same state vocabulary as PositionView/CalendarView: in_season,
    off_season (the season that just finished, with its final table), or
    no_season (before any season has ever been declared).
    """

    def get(self, request):
        position = current_position(now())
        if position.season is None:
            return Response(StandingsSerializer({
                "state": position.state, "season": None, "standings": [],
            }).data)

        table = standings(position.season)
        payload = {
            "state": position.state,
            "season": position.season.number,
            "standings": [
                {
                    "rank": rank,
                    "team": {"id": entry["team"].pk, "name": entry["team"].name, "code": entry["team"].code},
                    "points": entry["points"],
                }
                for rank, entry in enumerate(table, start=1)
            ],
        }
        return Response(StandingsSerializer(payload).data)


class StaffView(APIView):
    """The caller's own team's staff: the hired trainer, or the pool to
    hire from.

    No team id in the URL — the team is always the caller's own via
    team_for(), the same pattern as SquadView and RiderListView. Falls
    back to the project default, IsAuthenticated — do not re-add AllowAny.

    The pool is only populated in the response when the slot is empty: a
    team with a trainer has nothing to hire, and shipping the pool anyway
    would invite the SPA to offer a hire the API would reject.
    """

    def get(self, request):
        team = team_for(request.user)
        if team is None:
            return Response({"detail": "You do not manage a team."}, status=403)

        trainer = trainer_for(team)
        pool = [] if trainer is not None else list(available_trainers())
        return Response(StaffSerializer({"trainer": trainer, "pool": pool}).data)


class HireTrainerView(APIView):
    """Hire one pool trainer into the caller's empty slot.

    409, not 400, for "already hired" and "slot occupied": the request is
    well-formed but the world's state refuses it — the same split
    ClaimTeamView documents.
    """

    def post(self, request):
        team = team_for(request.user)
        if team is None:
            return Response({"detail": "You do not manage a team."}, status=403)

        serializer = HireTrainerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            hire_trainer(team, serializer.validated_data["trainer_id"])
        except (TrainerNotAvailable, SlotOccupied) as exc:
            return Response({"detail": str(exc)}, status=409)

        return Response(status=204)


class FireTrainerView(APIView):
    """Return the caller's trainer to the shared pool. POST, not DELETE —
    nothing is destroyed; the trainer survives in the pool."""

    def post(self, request):
        team = team_for(request.user)
        if team is None:
            return Response({"detail": "You do not manage a team."}, status=403)

        try:
            fire_trainer(team)
        except NoTrainerHired as exc:
            return Response({"detail": str(exc)}, status=409)

        return Response(status=204)


class TrainingView(APIView):
    """The caller's team's weekly training: the current focus and the last
    rollover's visible changes.

    No team id in the URL — the team is always the caller's own via
    team_for(), the same pattern as StaffView. GET always returns the whole
    payload; PUT sets the focus. A team without a trainer gets a 409 on PUT
    (well-formed request, world state refuses it) and a null `focus` with
    `has_trainer = false` on GET.
    """

    def get(self, request):
        team = team_for(request.user)
        if team is None:
            return Response({"detail": "You do not manage a team."}, status=403)

        return Response(TrainingSerializer({
            "has_trainer": trainer_for(team) is not None,
            "focus": focus_for(team),
            "options": list(ENGINE_ATTRIBUTES),
            "last_week": latest_report(team),
        }).data)

    def put(self, request):
        team = team_for(request.user)
        if team is None:
            return Response({"detail": "You do not manage a team."}, status=403)

        serializer = TrainingFocusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            set_focus(team, serializer.validated_data["attribute"])
        except NoTrainerHired as exc:
            return Response({"detail": str(exc)}, status=409)

        return Response(status=204)


class FinancesView(APIView):
    """The caller's own team's ledger: the running balance and its full
    history, newest first, each entry carrying the balance after it was
    written.

    No team id in the URL — the team is always the caller's own via
    team_for(), the same pattern as StaffView. A user with no team gets an
    empty ledger rather than a 403, so the Finances screen renders its calm
    empty state instead of an error.

    `balance_after` is computed here per D7: walk the entries in
    chronological order accumulating a running total, then reverse into the
    newest-first order the SPA displays. Doing it newest-first by
    subtracting is the natural first attempt and it is off-by-one — the
    oldest entry's `balance_after` must equal the starting balance.
    """

    def get(self, request):
        team = team_for(request.user)
        if team is None:
            return Response(FinancesSerializer({"balance": 0, "entries": []}).data)

        entries = list(entries_for(team))
        running = 0
        for entry in reversed(entries):            # chronological, oldest first
            running += entry.amount
            entry.balance_after = running

        return Response(FinancesSerializer({
            "balance": balance_for(team),
            "entries": entries,
        }).data)
