from __future__ import annotations

import brotli
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.db.models import Prefetch, Sum
from django.http import FileResponse, Http404, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from competitions.models import MarkerPoints, RacePoints
from competitions.scoring import (
    GC_POINTS_BY_POSITION,
    MOUNTAIN_PLACES,
    POINTS_BY_POSITION,
    SPRINT_PLACES,
    gc_points_for,
    gc_prize_for,
    mountain_points_for,
    points_for,
    prize_for,
    sprint_points_for,
    stage_points_for,
    stage_prize_for,
)
from competitions.services import standings
from economy.models import FanbaseEntry, LedgerEntry
from economy.services import (
    AlreadySponsored,
    OfferNotAvailable,
    active_contract,
    balance_for,
    charge_development_squad_fee,
    charge_trainer_fee,
    charge_transfer_fee,
    ensure_offer_round,
    entries_for,
    fanbase_entries_for,
    fanbase_for,
    latest_salary_review,
    offers_for,
    payroll_for,
    sign_offer,
)
from economy.solvency import EMBARGO_MESSAGE, SolvencyStatus, is_embargoed, solvency_status
from economy.sponsors import PROFILES_BY_KEY
from racing.models import (
    SQUAD_SIZE,
    MarkerCrossing,
    Race,
    RaceLog,
    RaceMarker,
    RaceSquad,
    RaceSquadRider,
    StageRace,
)
from racing.services import SquadError, carried_squad, general_classification, set_squad, suggested_squad
from riders.development_squad import (
    LEVELS,
    CannotDowngrade,
    LevelLocked,
    SameLevel,
    SquadAlreadyOpen,
    SquadNotOpen,
    UnknownLevel,
    change_level as change_squad_level,
    close_squad,
    level_fee as squad_level_fee,
    level_status as squad_level_status,
    open_squad,
    squad_for,
    weekly_cost as squad_weekly_cost,
)
# Aliased, not shadowed: staff.services.InsufficientFunds is imported
# unaliased above, and the two are unrelated classes. Catching the wrong one
# turns a 409 the player should see into a 500.
from riders.development_squad import InsufficientFunds as SquadInsufficientFunds
from riders.models import (
    ENGINE_ATTRIBUTES,
    DevelopmentSquad,
    Rider,
    RiderAttributeSnapshot,
)
from riders.pricing import strength, weekly_salary_for
from riders.youth_intake import INTAKE_BATCH_SIZE, INTAKE_INTERVAL_WEEKS, is_intake_week
from riders.youth_triage import (
    GRADUATE_WINDOW_WEEKS,
    SPELL_WEEKS,
    NotYourProspect,
    ProspectListed,
    RosterFull as SquadRosterFull,
    TriageError,
    discard,
    graduates,
    in_squad,
    promote,
)
from schedule.models import SEASON_WEEKS, Week
from schedule.services import current_position, weeks_ago_cutoff, weeks_opened_between
from staff.pricing import hire_fee, weekly_salary
from staff.services import (
    InsufficientFunds,
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
from teams.models import ManagerialSpell, Team
from teams.services import NoTeamAvailable, claim_team
from transfers.models import Auction, Bid
from transfers.pricing import market_value_for
from transfers.services import (
    ROSTER_CAP,
    AuctionAlreadyExists,
    AuctionNotOpen,
    BidTooLow,
    FORCED_SALE_ROSTER_FLOOR,
    InsufficientFunds as TransferInsufficientFunds,
    RiderNotAvailable,
    RiderNotOnRoster,
    RosterAtFloor,
    RosterFull,
    SelfBid,
    cancel_listings,
    cancel_open_auctions,
    cancel_unowned_listings,
    force_list_for_auction,
    free_agents,
    list_for_auction,
    place_bid,
    release_rider,
    sign_free_agent,
    withdraw_bids,
)
from world.services import now

from accounts.views import LoginView as AccountsLoginView

from .rider_profile import rider_profile
from .services import touch_last_seen
from .serializers import (
    AuctionMarketSerializer,
    CalendarSerializer,
    ClaimTeamSerializer,
    ClockSerializer,
    DevelopmentSquadLevelChoiceSerializer,
    DevelopmentSquadSerializer,
    FinancesSerializer,
    FreeAgentPoolSerializer,
    HireTrainerSerializer,
    ListForAuctionSerializer,
    MeSerializer,
    MeTeamSerializer,
    MyBidStatusSerializer,
    PlaceBidSerializer,
    PositionSerializer,
    RaceDetailSerializer,
    RaceResultsSerializer,
    ReleaseRiderSerializer,
    RiderProfileSerializer,
    RiderSerializer,
    RosterSerializer,
    SignFreeAgentSerializer,
    SquadSerializer,
    SquadWriteSerializer,
    SignOfferSerializer,
    SolvencySerializer,
    SponsorsSerializer,
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


def _embargo_response(team) -> Response | None:
    """The 409 an insolvent team gets for any action that adds cost or spends
    cash (#27), or None when the team is free to act. Checked here rather than
    in the services because transfers/, staff/ and riders/ may not import
    economy/ — the same reason the affordability checks live in api/. Callers
    run it before validating the payload, so the refusal never depends on its
    shape."""
    if is_embargoed(team):
        return Response({"detail": EMBARGO_MESSAGE}, status=409)
    return None


def _regular_costs(team) -> tuple[int, int]:
    """(trainer weekly salary, development squad weekly cost) for one team —
    the two regular outgoings economy/ may not look up itself."""
    trainer = trainer_for(team)
    squad = squad_for(team)
    return (
        weekly_salary(trainer) if trainer is not None else 0,
        squad_weekly_cost(squad.level) if squad is not None else 0,
    )


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


def _stage_race_ref_payload(race) -> dict | None:
    """A race's stage-race context, or None for a one-day race.

    Reads `race.stage_race.stages.all()` — never `.count()` — so a caller
    that has prefetched `stage_race__stages` pays no extra query; one that
    has not still works, just without the saving.
    """
    if race.stage_race_id is None:
        return None
    return {
        "id": race.stage_race.pk,
        "name": race.stage_race.name,
        "stage_number": race.stage_number,
        "stage_count": len(race.stage_race.stages.all()),
    }


def _race_payload(race) -> dict:
    return {
        "id": race.pk,
        "name": race.name,
        "starts_at": race.starts_at,
        "status": race.status,
        "distance_km": _distance_km(race),
        "stage_race": _stage_race_ref_payload(race),
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

        # stage_race__stages: every race's stage-race context and its
        # sibling stage count come from this one prefetch — see
        # _stage_race_ref_payload, which reads .all() rather than .count()
        # so the query never grows with how many stages a tour has.
        weeks = (
            position.season.weeks
            .prefetch_related("races__stage_race__stages")
            .order_by("number")
        )
        return Response(CalendarSerializer({
            "state": position.state,
            "season": position.season.number,
            "current_week": position.week.number if position.week else None,
            "weeks": [_week_payload(w) for w in weeks],
        }).data)


class LoginView(AccountsLoginView):
    """accounts' login, plus stamping the game-time last-seen.

    The stamp lives here rather than in accounts/views.py because accounts/
    imports nothing (AGENTS.md) and this needs world.services.now() — see
    accounts/README.md, Last seen is game time. Subclassed rather than
    reimplemented so the authentication logic, the vague failure message and
    the response shape all stay in one place.

    Routed in api/urls.py ahead of include("accounts.urls"), so this is the
    view that actually serves POST /api/accounts/login/.
    """

    def post(self, request):
        response = super().post(request)
        if response.status_code == 200 and request.user.is_authenticated:
            # is_authenticated is only true here because super().post()
            # already called login(), which populates request.user.
            touch_last_seen(request.user, now())
        return response


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
        lost_team = None
        if user.is_authenticated and team is None:
            spell = (
                ManagerialSpell.objects.filter(manager=user, acknowledged_at__isnull=True)
                .order_by("-ended_at")
                .first()
            )
            if spell is not None:
                lost_team = {
                    "spell": spell.pk,
                    "name": spell.team_name,
                    "code": spell.team_code,
                    "reason": spell.get_reason_display(),
                    "ended_at": spell.ended_at,
                }
        payload = {
            "authenticated": user.is_authenticated,
            "display_name": user.display_name if user.is_authenticated else None,
            "team": {"id": team.pk, "name": team.name, "code": team.code} if team else None,
            "lost_team": lost_team,
        }
        return Response(MeSerializer(payload).data)


def _later_stage(race) -> bool:
    return race.stage_number is not None and race.stage_number > 1


def _squad_payload(race, team, rider_ids: list[int], leader_id: int | None, *, saved: bool) -> dict:
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
        # A later stage's squad is carried from stage 1, never chosen here
        # — see racing/README.md, *Stage races*, and set_squad's own
        # refusal for the write side of this rule.
        "editable": race.status == Race.Status.SCHEDULED and not _later_stage(race),
        "saved": saved,
        "squad_size": len(rider_ids),
        "candidates": candidates,
        "stage_race": (
            {"name": race.stage_race.name, "stage_number": race.stage_number}
            if race.stage_race_id else None
        ),
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

        if _later_stage(race):
            # Never suggested_squad here: that falls back through
            # previous_squad (most recent race before this one, by
            # starts_at), which is the wrong rule for a stage — the squad
            # is always stage 1's, carried forward, never "whatever this
            # team raced last". See racing/README.md, *Stage races*.
            rider_ids, leader_id = carried_squad(race, team)
            payload = _squad_payload(race, team, rider_ids, leader_id, saved=True)
            return Response(SquadSerializer(payload).data)

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

    The claim, the withdrawal of the team's standing bids and the cancellation
    of its open listings share one transaction: a new manager inherits neither
    the team's bids (#30) nor its listings (#114).

    409 for both "already managing" and "no team available": the request is
    well-formed, but the world's state refuses it. 400 is reserved for a
    malformed name or code.
    """

    def post(self, request):
        if team_for(request.user) is not None:
            return Response({"detail": "You already manage a team."}, status=409)

        serializer = ClaimTeamSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        at = now()
        try:
            with transaction.atomic():
                team = claim_team(
                    request.user,
                    name=serializer.validated_data["name"],
                    code=serializer.validated_data["code"],
                    at=at,
                )
                withdraw_bids(team, at=at)
                # Every listing goes, the squad's released graduates' with
                # the rest: they all carry this team as seller (#114, #34).
                cancel_listings(team, at=at)
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


class AcknowledgeSpellView(APIView):
    """Mark the ex-manager's lost-team message as seen, so it is shown once.

    404 for a spell that is not the caller's — never 403, which would
    confirm the row exists.
    """

    def post(self, request, spell_id: int):
        updated = ManagerialSpell.objects.filter(
            pk=spell_id, manager=request.user, acknowledged_at__isnull=True
        ).update(acknowledged_at=timezone.now())
        if updated == 0:
            return Response({"detail": "No such message."}, status=404)
        return Response(status=204)


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

        riders = list(Rider.objects.filter(team=team))
        return Response(RosterSerializer({
            "riders": riders,
            "squad_value": sum(market_value_for(r) for r in riders),
            "salary_review": latest_salary_review(team),
        }, context={
            "team": team,
            "weeks_opened": _cooldown_weeks_opened(team, now()),
        }).data)


class RiderProfileView(APIView):
    """One rider's full profile — identity, current team, freshness,
    salary, market value, attributes, attribute history, race history and
    career totals. Readable by any authenticated manager, whatever their
    team, like RaceDetailView — not scoped to the caller's team, and no
    "this is your rider" branch. See specs/rider-detail-view-plan.md, D1-D2.
    """

    def get(self, request, rider_id: int):
        rider = get_object_or_404(
            Rider.objects.select_related("team", "development_squad__team"), pk=rider_id,
        )
        profile = rider_profile(rider, at=now())
        return Response(RiderProfileSerializer(rider, context={"profile": profile}).data)


def _cooldown_weeks_opened(team, boundary) -> int:
    """In-season weeks opened since `team` was claimed, for the claim-cooldown
    exemption (transfers/README.md, *Free agents*).

    `transfers/` may not import `schedule/` (AGENTS.md), so api/ — the only
    app allowed to know everything — counts for it via
    schedule.services.weeks_opened_between, the same Week-row rule
    `world/` uses for inactivity and expiry: only in-season weeks count, so
    an off-season gap contributes nothing. 0 for a team that was
    never claimed (`managed_since` is null and there is no cooldown to
    run out)."""
    if team.managed_since is None:
        return 0
    return weeks_opened_between(team.managed_since, boundary)


class FreeAgentsView(APIView):
    """Every free agent in the pool, plus the caller's balance.

    The pool is the same for every manager, so no team scoping applies to
    the listing — but a team is still required (403 without one), matching
    RiderListView's own-team gate, because the balance key in the response
    is the caller's.
    """

    def get(self, request):
        team = team_for(request.user)
        if team is None:
            return Response({"detail": "You do not manage a team."}, status=403)

        return Response(FreeAgentPoolSerializer({
            "riders": list(free_agents()),
            "balance": balance_for(team),
        }).data)


class SignFreeAgentView(APIView):
    """Sign one free agent onto the caller's team, debiting the signing fee.

    409, not 400, for RiderNotAvailable, RosterFull and
    TransferInsufficientFunds: the request itself is well-formed — the
    world's state refuses it — the same split ClaimTeamView and
    HireTrainerView document.
    """

    def post(self, request):
        team = team_for(request.user)
        if team is None:
            return Response({"detail": "You do not manage a team."}, status=403)

        embargoed = _embargo_response(team)
        if embargoed is not None:
            return embargoed

        serializer = SignFreeAgentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        at = now()

        def charge(rider, fee):
            if fee > 0 and balance_for(team) < fee:
                raise TransferInsufficientFunds(
                    "You cannot afford this rider's signing fee."
                )
            if fee > 0:
                charge_transfer_fee(
                    team, amount=-fee, at=at, description=f"Signed {rider.name}",
                )

        try:
            sign_free_agent(
                team, serializer.validated_data["rider_id"], at=at, charge=charge,
            )
        except (RiderNotAvailable, RosterFull, TransferInsufficientFunds) as exc:
            return Response({"detail": str(exc)}, status=409)

        return Response(status=204)


class ReleaseRiderView(APIView):
    """Send one of the caller's own riders to the free-agent pool.

    Charges severance unless the claim cooldown exempts the rider — see
    transfers/README.md, *Free agents*. 409, not 400, for
    RiderNotOnRoster: the request is well-formed, the world's state refuses
    it. Release never fails on affordability — it is 0 within the cooldown
    and the game cannot hold a rider hostage, so severance is charged even
    when the balance is below it (transfers.services.release_rider's job is
    the roster change; the charge entry simply records what is owed).
    """

    def post(self, request):
        team = team_for(request.user)
        if team is None:
            return Response({"detail": "You do not manage a team."}, status=403)

        serializer = ReleaseRiderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        at = now()

        def charge(rider, fee):
            if fee > 0:
                charge_transfer_fee(
                    team, amount=-fee, at=at, description=f"Released {rider.name}",
                )

        try:
            release_rider(
                team,
                serializer.validated_data["rider_id"],
                at=at,
                weeks_opened=_cooldown_weeks_opened(team, at),
                charge=charge,
            )
        except RiderNotOnRoster as exc:
            return Response({"detail": str(exc)}, status=409)

        return Response(status=204)


class AuctionMarketView(APIView):
    """Every open auction, plus the caller's balance. Mirrors
    FreeAgentsView exactly. `min_next_bid`, `is_own_listing` and `bids`
    are computed here, not in the serializer — none is a plain attribute
    of an Auction row. Bidding is not anonymous (spec, *Rules and edge
    cases*): every listing carries its full bid history, newest first,
    each with the bidding team's name."""

    def get(self, request):
        team = team_for(request.user)
        if team is None:
            return Response({"detail": "You do not manage a team."}, status=403)

        auctions_qs = (
            Auction.objects.filter(status=Auction.Status.OPEN)
            .select_related("rider")
            .prefetch_related(
                Prefetch("bids", queryset=Bid.objects.live().select_related("bidder_team"))
            )
        )
        auctions = []
        for auction in auctions_qs:
            bids = list(auction.bids.all())
            # place_bid accepts the reserve itself as the opening bid
            # (spec items 3-4) — the increment only applies once a bid
            # already exists to clear, matching transfers.services.
            # place_bid's own minimum exactly.
            min_next_bid = (
                auction.current_price if not bids
                else auction.current_price + auction.min_increment
            )
            auctions.append({
                "id": auction.pk,
                "rider": auction.rider,
                "current_price": auction.current_price,
                "min_next_bid": min_next_bid,
                "deadline": auction.deadline,
                "is_own_listing": auction.seller_team_id == team.pk,
                "forced": auction.forced,
                "bids": [
                    {
                        "team_name": bid.bidder_team.name,
                        "amount": bid.amount,
                        "placed_at": bid.placed_at,
                    }
                    for bid in bids
                ],
            })
        return Response(AuctionMarketSerializer({
            "auctions": auctions,
            "balance": balance_for(team),
        }).data)


class ListForAuctionView(APIView):
    """List one of the caller's own riders. 409 for AuctionAlreadyExists /
    RiderNotOnRoster (request well-formed, world state refuses it — same
    split as SignFreeAgentView)."""

    def post(self, request):
        team = team_for(request.user)
        if team is None:
            return Response({"detail": "You do not manage a team."}, status=403)

        serializer = ListForAuctionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            list_for_auction(team, serializer.validated_data["rider_id"], at=now())
        except (RiderNotOnRoster, AuctionAlreadyExists) as exc:
            return Response({"detail": str(exc)}, status=409)

        return Response(status=204)


class ForceSellView(APIView):
    """Sell one of the caller's own riders under insolvency (#27): the rider
    leaves the roster now, so the wage stops now, and is auctioned with no
    severance — a sale pays the team, no sale makes the rider a free agent.
    Only an insolvent team may; a solvent one has the ordinary listing and
    release. 409 for everything the world's state refuses, as elsewhere."""

    def post(self, request):
        team = team_for(request.user)
        if team is None:
            return Response({"detail": "You do not manage a team."}, status=403)

        serializer = ListForAuctionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        if not is_embargoed(team):
            return Response({"detail": "Only an insolvent team can force a sale."}, status=409)

        try:
            force_list_for_auction(team, serializer.validated_data["rider_id"], at=now())
        except (RiderNotOnRoster, RosterAtFloor) as exc:
            return Response({"detail": str(exc)}, status=409)

        return Response(status=204)


class PlaceBidView(APIView):
    """Place a bid on an open auction. Balance checked here (Design
    decision 8) against economy.services.balance_for BEFORE calling
    transfers.services.place_bid — no charge happens yet, so there is no
    injected charge callback on this path, unlike sign_free_agent."""

    def post(self, request, auction_id):
        team = team_for(request.user)
        if team is None:
            return Response({"detail": "You do not manage a team."}, status=403)

        embargoed = _embargo_response(team)
        if embargoed is not None:
            return embargoed

        serializer = PlaceBidSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        amount = serializer.validated_data["amount"]

        if balance_for(team) < amount:
            return Response({"detail": "You cannot afford this bid."}, status=409)

        try:
            place_bid(auction_id, team, amount, at=now())
        except (AuctionNotOpen, BidTooLow, SelfBid) as exc:
            return Response({"detail": str(exc)}, status=409)

        return Response(status=204)


class MyBidsView(APIView):
    """Every auction the caller's team has an active bid on, with
    is_high_bidder — backs spec item 8's outbid notice. Read-only,
    polled by the frontend the same way FreeAgentsView is.

    Two queries regardless of how many auctions the team has bid on: the
    auction list itself, and one prefetch of the team's own bids across
    all of them — not one `bids.filter(...).first()` per row, which would
    cost an extra query per auction on an endpoint the Dashboard and
    Transfers screens both poll every 30s.
    """

    def get(self, request):
        team = team_for(request.user)
        if team is None:
            return Response({"detail": "You do not manage a team."}, status=403)

        my_bids = Bid.objects.live().filter(bidder_team=team).order_by("-amount", "-placed_at")
        auctions = (
            Auction.objects.filter(
                status=Auction.Status.OPEN,
                bids__bidder_team=team,
                bids__withdrawn_at__isnull=True,
            )
            .distinct()
            .select_related("rider")
            .prefetch_related(Prefetch("bids", queryset=my_bids, to_attr="my_bids"))
        )
        rows = []
        for auction in auctions:
            my_last_bid = auction.my_bids[0]
            rows.append({
                "auction_id": auction.pk,
                "rider_name": auction.rider.name,
                "my_last_bid": my_last_bid.amount,
                "current_price": auction.current_price,
                "is_high_bidder": my_last_bid.amount == auction.current_price,
                "deadline": auction.deadline,
            })
        return Response(MyBidStatusSerializer(rows, many=True).data)


def _marker_payload(marker) -> dict:
    """A marker as the course preview and the results screen both show it.
    `weight` is null on a mountain marker and `category` null on a sprint —
    each vocabulary belongs to the kind it was authored for."""
    is_sprint = marker.kind == RaceMarker.Kind.SPRINT
    if is_sprint:
        points = [sprint_points_for(marker.weight, p) for p in range(1, SPRINT_PLACES + 1)]
    else:
        points = [mountain_points_for(marker.category, p) for p in range(1, MOUNTAIN_PLACES + 1)]
    return {
        "id": marker.pk,
        "kind": marker.kind,
        "name": marker.name,
        "distance": marker.distance,
        "weight": marker.weight if is_sprint else None,
        "category": None if is_sprint else marker.category,
        "points": points,
    }


class RaceDetailView(APIView):
    """One race's own facts — identity, status, when, how far, and the
    course profile. Unlike SquadView this is not about the caller's team:
    any authenticated manager may read any race, including one their team
    did not start. See specs/race-detail-view-plan.md, D1."""

    def get(self, request, race_id: int):
        race = get_object_or_404(Race, pk=race_id)
        # A stage uses the reduced stage table; a one-day race the
        # unchanged one-day table — same switch racing/README.md's scoring
        # functions make (specs/archive/stage-races.md, Decisions taken).
        points_for_position = stage_points_for if race.stage_race_id else points_for
        prize_for_position = stage_prize_for if race.stage_race_id else prize_for
        payload = {
            "id": race.pk,
            "name": race.name,
            "status": race.status,
            "starts_at": race.starts_at,
            "distance_km": _distance_km(race),
            "course": race.course,
            "payout": [
                {"position": p, "points": points_for_position(p), "prize": prize_for_position(p)}
                for p in sorted(POINTS_BY_POSITION)
            ],
            "gc_payout": [
                {"position": p, "points": gc_points_for(p), "prize": gc_prize_for(p)}
                for p in sorted(GC_POINTS_BY_POSITION)
            ] if race.stage_race_id else [],
            "markers": [
                _marker_payload(m) for m in race.markers.all()  # model ordering: distance, pk
            ],
            # Whether the SPA can offer a Watch race. A row with a file is
            # enough: stat'ing the file here would be a network round trip
            # per detail view once logs move to object storage, and a log
            # that has gone missing surfaces on the replay screen itself
            # (D5).
            "has_replay": RaceLog.objects.filter(race=race).exclude(file="").exists(),
            "stage_race": _race_detail_stage_race_payload(race),
        }
        return Response(RaceDetailSerializer(payload).data)


def _race_detail_stage_race_payload(race) -> dict | None:
    if race.stage_race_id is None:
        return None
    stages = list(race.stage_race.stages.order_by("stage_number"))
    return {
        "id": race.stage_race.pk,
        "name": race.stage_race.name,
        "stage_number": race.stage_number,
        "stage_count": len(stages),
        "stages": [
            {"id": s.pk, "stage_number": s.stage_number, "starts_at": s.starts_at, "status": s.status}
            for s in stages
        ],
    }


def _accepts_brotli(header: str) -> bool:
    """Does this request's Accept-Encoding offer brotli? Browsers only
    advertise it on a secure context, so a plain-HTTP deploy or an odd client
    gets the decompressed body instead (D4). A token refused with `q=0` — in
    any equivalent spelling, trailing zeroes included — is not offered."""
    for token in header.split(","):
        parts = [p.strip() for p in token.split(";")]
        if parts[0] != "br":
            continue
        for param in parts[1:]:
            if param.startswith("q="):
                try:
                    if float(param[2:]) <= 0:
                        return False
                except ValueError:
                    # An unreadable q-value is not a refusal; treat the token
                    # as offered rather than guessing what the client meant.
                    pass
        return True
    return False


class RaceLogView(APIView):
    """A finished race's stored tick-by-tick log, for the replay screen.

    Streamed from storage rather than linked as media: `/media` is only
    served under DEBUG, bypasses auth, and cannot send `Content-Encoding` —
    without which the browser hands the player raw brotli bytes and
    `parseRaceLog` throws on line 1. A 0.75 MB body through the app server
    is fine at this scale, and IsAuthenticated is the project default
    (D3). When logs move to object storage this view becomes a redirect to a
    signed URL — a change to this one view.
    """

    def get(self, request, race_id: int):
        race = get_object_or_404(Race, pk=race_id)
        if race.status != Race.Status.FINISHED:
            raise Http404("race has not finished")

        log = RaceLog.objects.filter(race=race).exclude(file="").first()
        if log is None:
            raise Http404("race has no log")
        try:
            handle = log.file.open("rb")
        except FileNotFoundError:
            raise Http404("log file missing")

        if _accepts_brotli(request.META.get("HTTP_ACCEPT_ENCODING", "")):
            # content_type explicit: Django would otherwise guess from the
            # .br filename and label this application/x-brotli.
            response = FileResponse(handle, content_type="application/x-ndjson")
            response["Content-Encoding"] = "br"
        else:
            with handle:
                body = brotli.decompress(handle.read())
            response = HttpResponse(body, content_type="application/x-ndjson")
        # The same URL answers two different bodies, and the log is immutable
        # once written, so a day in the player's own cache is safe; `private`
        # keeps it out of shared caches, which must not hold a response to an
        # authenticated request.
        response["Vary"] = "Accept-Encoding"
        response["Cache-Control"] = "private, max-age=86400"
        return response


def _result_row(result, team) -> dict:
    return {
        "position": result.position,
        "rider": {"id": result.rider.pk, "name": result.rider.name},
        "team": {"id": team.pk, "name": team.name, "code": team.code} if team is not None else None,
        "finish_time": result.finish_time,
        "group_time": result.group_time,
        "finished": result.finish_time is not None,
    }


def _crossing_payload(crossing, team_by_rider, scored_crossing) -> dict:
    team = team_by_rider.get(crossing.rider_id)
    return {
        "position": crossing.position,
        "rider": {"id": crossing.rider.pk, "name": crossing.rider.name},
        # The team the rider raced for, not their current one — same rule as
        # the results rows above.
        "team": (
            {"id": team.pk, "name": team.name, "code": team.code}
            if team is not None else None
        ),
        # None for a mountain crossing, and for a sprint crossing whose
        # teammate already scored the team's one row at this marker.
        "points": scored_crossing.get((crossing.marker_id, crossing.rider_id)),
    }


#: How many crossings per marker the results screen shows — D11, raised to
#: match SPRINT_PLACES so every scoring position is visible. The full order
#: stays in the database for the features above the markers.
MARKER_PLACES_SHOWN = SPRINT_PLACES


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

        results = race.results.select_related("rider").order_by("position")
        team_by_rider = {
            m.rider_id: m.squad.team
            for m in RaceSquadRider.objects
                .filter(squad__race=race)
                .select_related("squad__team")
        }
        markers = (
            race.markers
            .prefetch_related(Prefetch(
                "crossings",
                queryset=MarkerCrossing.objects
                    .filter(position__lte=MARKER_PLACES_SHOWN)
                    .select_related("rider"),
            ))
        )
        scored_crossing = {
            (mp.marker_id, mp.rider_id): mp.points
            for mp in MarkerPoints.objects.filter(marker__race=race)
        }
        markers_payload = [
            {
                **_marker_payload(m),
                "crossings": [
                    _crossing_payload(c, team_by_rider, scored_crossing)
                    for c in m.crossings.all()  # model ordering: marker, position
                ],
            }
            for m in markers.all()  # model ordering: distance, pk
        ]
        # kind=RACE: the final stage of a completed tour also carries a
        # kind=GC row (competitions.models.RacePoints.Kind) — without this
        # filter a GC award would show up in the stage's own team-points
        # table (see racing/README.md, *Stage races*, and the plan's Risks).
        points = (
            race.points.filter(kind=RacePoints.Kind.RACE)
            .select_related("team").order_by("position")
        )
        scored = {p.team_id: p for p in points}
        # Keyed by kind as well as team: summing every MarkerPoints row into
        # sprint_points would quietly put mountain points in the sprint column.
        marker_by_team_kind = {
            (row["team_id"], row["marker__kind"]): row["total"]
            for row in MarkerPoints.objects
                .filter(marker__race=race)
                .values("team_id", "marker__kind")
                .annotate(total=Sum("points"))
        }

        def _markers_for(team_id) -> int:
            """Everything this team scored at a marker, either kind."""
            return sum(marker_by_team_kind.get((team_id, kind), 0) for kind in RaceMarker.Kind)

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
                "finish_points": p.points,
                "sprint_points": marker_by_team_kind.get(
                    (p.team_id, RaceMarker.Kind.SPRINT), 0),
                "mountain_points": marker_by_team_kind.get(
                    (p.team_id, RaceMarker.Kind.MOUNTAIN), 0),
                "points": p.points + _markers_for(p.team_id),
                "prize": prize_by_team.get(p.team_id, 0),
            }
            for p in points
        ] + sorted(
            [
                {
                    "team": {"id": t.pk, "name": t.name, "code": t.code},
                    "position": None,
                    "finish_points": 0,
                    "sprint_points": marker_by_team_kind.get(
                        (t.pk, RaceMarker.Kind.SPRINT), 0),
                    "mountain_points": marker_by_team_kind.get(
                        (t.pk, RaceMarker.Kind.MOUNTAIN), 0),
                    "points": _markers_for(t.pk),
                    "prize": prize_by_team.get(t.pk, 0),
                }
                for t in starters
                if t.pk not in scored
            ],
            key=lambda row: (-_markers_for(row["team"]["id"]), row["team"]["name"]),
        )

        payload = {
            "race": {
                "id": race.pk, "name": race.name, "status": race.status,
                "stage_race": _stage_race_ref_payload(race),
            },
            "results": [_result_row(r, team_by_rider.get(r.rider_id)) for r in results],
            "points": points_payload,
            "markers": markers_payload,
            "gc": _gc_payload(race),
        }
        return Response(RaceResultsSerializer(payload).data)


def _gc_payload(race) -> dict | None:
    """None for a one-day race. Otherwise the GC as of THIS race's stage —
    racing.services.general_classification(through_stage=...), D6 — plus
    the frozen award once the whole stage race has completed (D11)."""
    if race.stage_race_id is None:
        return None

    stage_race = race.stage_race
    entries = general_classification(stage_race, through_stage=race.stage_number)
    leader_time = entries[0].gc_time if entries else 0.0
    team_by_rider = {
        m.rider_id: m.squad.team
        for m in RaceSquadRider.objects
            .filter(squad__race__stage_race=stage_race, squad__race__stage_number=1)
            .select_related("squad__team")
    }
    rider_by_id = {r.pk: r for r in Rider.objects.filter(pk__in=[e.rider_id for e in entries])}

    final = stage_race.is_complete() and race.stage_number == stage_race.final_stage().stage_number
    gc_points_payload = []
    if final:
        final_stage = stage_race.final_stage()
        gc_points = final_stage.points.filter(kind=RacePoints.Kind.GC).select_related("team").order_by("position")
        gc_prizes = (
            LedgerEntry.objects
            .filter(race=final_stage, kind=LedgerEntry.Kind.GC_PRIZE_MONEY)
            .values("team_id").annotate(total=Sum("amount"))
        )
        gc_prize_by_team = {p["team_id"]: p["total"] for p in gc_prizes}
        gc_points_payload = [
            {
                "team": {"id": p.team.pk, "name": p.team.name, "code": p.team.code},
                "position": p.position,
                "points": p.points,
                "prize": gc_prize_by_team.get(p.team_id, 0),
            }
            for p in gc_points
        ]

    return {
        "after_stage": race.stage_number,
        "final": final,
        "standings": [
            {
                "position": i,
                "rider": {"id": e.rider_id, "name": rider_by_id[e.rider_id].name},
                "team": (
                    {"id": t.pk, "name": t.name, "code": t.code}
                    if (t := team_by_rider.get(e.rider_id)) is not None else None
                ),
                "gc_time": e.gc_time,
                "gap": e.gc_time - leader_time,
            }
            for i, e in enumerate(entries, start=1)
        ],
        "points": gc_points_payload,
    }


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
        return Response(
            StaffSerializer(
                {"trainer": trainer, "pool": pool, "balance": balance_for(team)}
            ).data
        )


class HireTrainerView(APIView):
    """Hire one pool trainer into the caller's empty slot, debiting the
    hire fee.

    409, not 400, for "already hired", "slot occupied" and "cannot
    afford it": the request is well-formed but the world's state refuses
    it — the same split ClaimTeamView documents.
    """

    def post(self, request):
        team = team_for(request.user)
        if team is None:
            return Response({"detail": "You do not manage a team."}, status=403)

        embargoed = _embargo_response(team)
        if embargoed is not None:
            return embargoed

        serializer = HireTrainerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        def charge(trainer):
            fee = hire_fee(trainer)
            if balance_for(team) < fee:
                raise InsufficientFunds("You cannot afford this trainer's fee.")
            charge_trainer_fee(
                team,
                amount=-fee,
                at=now(),
                description=f"Hired {trainer.name}",
            )

        try:
            hire_trainer(team, serializer.validated_data["trainer_id"], charge=charge)
        except (TrainerNotAvailable, SlotOccupied, InsufficientFunds) as exc:
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


def _squad_charge(team):
    """The `charge` callback open_squad and change_level take, wired to the
    ledger. api/ is allowed to import both economy/ and riders/, but the
    functions themselves are not: riders/ may not import economy/ (AGENTS.md),
    so the debit arrives by injection (riders/README.md, *Development squad*).

    The balance check is here rather than in economy/ because refusing a
    change is a view-level concern — the ledger is append-only and never
    refuses anything.
    """
    def charge(amount, description):
        if balance_for(team) < amount:
            raise SquadInsufficientFunds("You cannot afford this.")
        charge_development_squad_fee(
            team, amount=-amount, at=now(), description=description,
        )
    return charge


def _next_intake_week(at):
    """The first declared Week after `at` that is an intake week, or None when
    no such week is declared yet — a season not yet loaded past this point, or
    no season at all. At most a few dozen Week rows exist, so a Python-side
    is_intake_week filter over one ordered query is simpler than
    reimplementing `% INTAKE_INTERVAL_WEEKS` in SQL, and it keeps the rule in
    the one place riders.youth_intake owns it.

    The Week row itself rather than its `{season, week}` position: the squad
    payload needs how many of that batch would be turned away, which is a
    count of free places and nothing else (#34).
    """
    for week in Week.objects.select_related("season").filter(
        starts_at__gt=at,
    ).order_by("starts_at"):
        if is_intake_week(week.number):
            return week
    return None


def _latest_intake_at(at):
    """starts_at of the last declared Week at or before `at` that is an
    intake week, or None if none has opened yet. This is what an arrival's
    intake_at is compared against for is_new (#33's plan, Design decision
    15) — the most recently opened intake week, not a rolling time window."""
    latest = None
    for week in Week.objects.filter(starts_at__lte=at).order_by("starts_at"):
        if is_intake_week(week.number):
            latest = week.starts_at
    return latest


class DevelopmentSquadView(APIView):
    """The caller's development squad: which level is open, and what each of
    the three costs and offers. GET only, and no team id in the URL — the team
    is always the caller's own via team_for(), the same pattern as StaffView.

    A closed squad is `level: null` with every level still priced, not an
    error and not a 404: "you have no squad" is a state this screen is built
    to show, not a missing resource.

    Each level carries `action` and `requires` — the server's own answer from
    `riders.development_squad.level_status` — rather than leaving the SPA to
    work out the ladder from `level` alone. That is the whole
    reason this endpoint exists in this shape: the rule that gates a level is
    a rule about the game, not about the screen, and deriving it twice is how
    a padlock and a 409 end up disagreeing. `locked` is a first-class answer,
    not the absence of one, and `requires` explains it, because a rung not yet
    reached and one already climbed past need different words.
    """

    def get(self, request):
        team = team_for(request.user)
        if team is None:
            return Response({"detail": "You do not manage a team."}, status=403)

        squad = squad_for(team)
        current_level = squad.level if squad is not None else None
        levels = []
        for _, terms in sorted(LEVELS.items()):
            status = squad_level_status(current_level, terms.level)
            levels.append(
                {
                    "level": terms.level,
                    "name": terms.name,
                    "weekly_cost": terms.weekly_cost,
                    "season_cost": terms.weekly_cost * SEASON_WEEKS,
                    # What moving onto this level costs. The same figure
                    # whether the squad is closed and this is the opening, or
                    # open one rung below and this is the upgrade — so the
                    # number on the card is the number that would be charged,
                    # and reaching the top means paying every fee on the way.
                    "fee": squad_level_fee(terms.level),
                    "places": terms.places,
                    "action": status.action,
                    # Why a locked level is locked, and null for every other
                    # action. Server-owned for the same reason the 409
                    # details are: it is a statement about the game, and the
                    # screen has no business re-deriving it.
                    "requires": status.note,
                }
            )

        at = now()
        # One map per derived value, built once for the whole squad and handed
        # to the serializers through context: this endpoint is asked about one
        # squad of at most ten riders, and a query per rider per figure is how
        # a squad screen ends up issuing thirty of them (#34).
        weeks_left = {}
        graduate_weeks_left = {}
        promotion_salaries = {}
        market_values = {}
        listed = {}

        if squad is not None:
            prospects = sorted(in_squad(squad), key=strength, reverse=True)
            finished = sorted(graduates(squad), key=strength, reverse=True)
            for rider in prospects:
                weeks_left[rider.pk] = _weeks_left(rider.intake_at, SPELL_WEEKS, at)
            for rider in finished:
                graduate_weeks_left[rider.pk] = _weeks_left(
                    rider.graduated_at, GRADUATE_WINDOW_WEEKS, at,
                )
                promotion_salaries[rider.pk] = weekly_salary_for(rider)
                market_values[rider.pk] = market_value_for(rider)
            for rider in prospects:
                promotion_salaries[rider.pk] = weekly_salary_for(rider)
            listed = {
                rider_id: True
                for rider_id in Auction.objects.filter(
                    status=Auction.Status.OPEN,
                    rider__in=list(prospects) + list(finished),
                ).values_list("rider_id", flat=True)
            }
            baselines = {
                snapshot.rider_id: snapshot
                for snapshot in RiderAttributeSnapshot.objects.filter(
                    rider__in=list(prospects) + list(finished), week__isnull=True,
                )
            }
            intake = {
                "every_weeks": INTAKE_INTERVAL_WEEKS,
                "batch_size": INTAKE_BATCH_SIZE,
                "next": _next_intake_payload(at, squad),
            }
            latest_intake_at = _latest_intake_at(at)
        else:
            prospects = []
            finished = []
            baselines = {}
            intake = None
            latest_intake_at = None

        return Response(DevelopmentSquadSerializer({
            "level": current_level,
            "levels": levels,
            "balance": balance_for(team),
            "places": LEVELS[current_level].places if squad is not None else None,
            "in_squad": len(prospects),
            "roster_count": team.riders.count(),
            "roster_cap": ROSTER_CAP,
            "riders": prospects,
            "graduates": finished,
            "intake": intake,
        }, context={
            "latest_intake_at": latest_intake_at,
            "weeks_left": weeks_left,
            "graduate_weeks_left": graduate_weeks_left,
            "promotion_salaries": promotion_salaries,
            "market_values": market_values,
            "listed": listed,
            "baselines": baselines,
        }).data)


def _weeks_left(started_at, total: int, at) -> int:
    """In-season weeks of `total` still to run from `started_at`, floored at
    1 (#34, Design decision 16).

    A count rather than a `{season, week}` position on purpose: the next
    season is often not declared yet, which would leave every rider a
    position-less "unknown" exactly when the player needs to know how long
    they have.

    It is `total` **less the weeks that have already opened**, matching the
    rules that end each wait: a prospect graduates and a graduate is released
    at the boundary where that count reaches `total`, so this is the number of
    boundaries before that happens — no more. The plan wrote `total + 1`, which
    is one too many for both, because the week a rider arrives in is the week
    whose opening has already been counted for them and the week they spend
    their arrival developing nothing (#33's rule that a newcomer first grows at
    the *next* boundary). The floor keeps a rider shown at 1 rather than 0 in
    the rare race between a boundary's tick and the screen reading it.

    schedule/ owns week counting (AGENTS.md); world/ just asks.
    """
    if started_at is None:
        return total
    return max(1, total - weeks_opened_between(started_at, at))


def _next_intake_payload(at, squad) -> dict | None:
    """The next intake week with how many of its batch would be turned away,
    or None when no intake week is declared yet.

    `arrivals_at_risk` is a projection, not a forecast: it says what happens
    if nothing changes before the week arrives, so promoting or discarding a
    prospect changes the number the player is warned with (#34, Design
    decision 14).

    **Riders who graduate by then are counted as gone**, because they will be:
    the tick graduates before it runs intake at the same boundary. Graduations
    land two weeks before an intake with a 14-week spell and a four-week
    interval, so leaving them out would warn a full squad about a batch that
    will in fact arrive — every cycle — and push the manager into discarding a
    rider for nothing. The cutoff is `schedule.services.weeks_ago_cutoff`
    taken at that week's boundary, the same call `world/` graduates with, so
    the warning and the tick cannot disagree about who has left.
    """
    week = _next_intake_week(at)
    if week is None:
        return None
    occupied = in_squad(squad)
    cutoff = weeks_ago_cutoff(week.starts_at, SPELL_WEEKS)
    if cutoff is not None:
        occupied = occupied.exclude(intake_at__lte=cutoff)
    free = max(0, LEVELS[squad.level].places - occupied.count())
    return {
        "season": week.season.number,
        "week": week.number,
        "arrivals_at_risk": max(0, INTAKE_BATCH_SIZE - free),
    }


class OpenDevelopmentSquadView(APIView):
    """Open the caller's development squad at the entry level, debiting that
    level's fee. Asking for any other level is a 409 `LevelLocked` from the
    service: the ladder is climbed, and there is no door into the upper floors
    however much the team can afford.

    409, not 400, for "already open", "cannot afford it" and "locked": the
    request is well-formed but the world's state refuses it — the same split
    HireTrainerView documents. An unknown level is a 400 from the serializer's
    ChoiceField, before this view runs.
    """

    def post(self, request):
        team = team_for(request.user)
        if team is None:
            return Response({"detail": "You do not manage a team."}, status=403)

        embargoed = _embargo_response(team)
        if embargoed is not None:
            return embargoed

        serializer = DevelopmentSquadLevelChoiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            open_squad(
                team,
                serializer.validated_data["level"],
                at=now(),
                charge=_squad_charge(team),
            )
        except (
            SquadAlreadyOpen,
            LevelLocked,
            UnknownLevel,
            SquadInsufficientFunds,
        ) as exc:
            return Response({"detail": str(exc)}, status=409)

        return Response(status=204)


class ChangeDevelopmentSquadLevelView(APIView):
    """Upgrade the caller's open development squad one level, debiting that
    level's full fee.

    Only the rung directly above the one held: skipping one is a 409
    `LevelLocked`, anything lower a 409 `CannotDowngrade` (close the squad
    instead), and the level already held a 409 `SameLevel` — all three from
    the service, none of them special-cased here.
    """
    def post(self, request):
        team = team_for(request.user)
        if team is None:
            return Response({"detail": "You do not manage a team."}, status=403)

        embargoed = _embargo_response(team)
        if embargoed is not None:
            return embargoed

        serializer = DevelopmentSquadLevelChoiceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            change_squad_level(
                team,
                serializer.validated_data["level"],
                charge=_squad_charge(team),
            )
        except (
            SquadNotOpen,
            SameLevel,
            LevelLocked,
            CannotDowngrade,
            UnknownLevel,
            SquadInsufficientFunds,
        ) as exc:
            return Response({"detail": str(exc)}, status=409)

        return Response(status=204)


class CloseDevelopmentSquadView(APIView):
    """Close the caller's development squad. POST, not DELETE — the same
    reasoning FireTrainerView gives, and here literally so: the squad row is
    deleted, but the opening fee already paid is in the ledger and stays there.

    Closing an already-closed squad is a 409 rather than a silent 204, so the
    SPA's post-close refresh is the only thing that reports success.

    **Any listing the team can no longer sell is cancelled in the same
    transaction** (#34). A released graduate's auction would otherwise stay
    biddable until its deadline, and a winner at that point would be refused
    by the very ownership check that would have caught it three days earlier.
    `close_squad` returning a falsy value — None, or a closure that did
    nothing — is a 409.
    """
    def post(self, request):
        team = team_for(request.user)
        if team is None:
            return Response({"detail": "You do not manage a team."}, status=403)

        at = now()
        with transaction.atomic():
            closed = close_squad(team, at=at)
            if not closed:
                return Response(
                    {"detail": "Your team has no development squad."}, status=409
                )
            cancel_unowned_listings(team, at=at)

        return Response(status=204)


class PromoteSquadRiderView(APIView):
    """Promote one of the caller's squad's riders onto the roster (#34).

    Works on a prospect *and* on a graduate: both are the team's to decide
    about, and promoting a graduate early is a legitimate choice rather than
    a loophole — the alternative the spec weighs is refusing it, and the
    league of consequences is worse than a manager paying a wage early.

    A roster at `ROSTER_CAP` is a 409 `RosterFull` rather than a refusal
    after the fact; the screen disables the button first, using the same
    `roster_count`/`roster_cap` the GET sends.

    **Promoting a listed graduate cancels their auction in the same
    transaction.** The squad screen keeps Promote on a listed rider — the
    sale is what a listing takes away, not the option of keeping them — so
    this is the button's only honest reading: the manager is choosing the
    rider over the bids, and the sale ends. Without it the auction would sit
    open over a rider now on the roster, and the winner at its deadline would
    take a player the team is also paying and fielding. This departs from
    the plan's Design decision 9, which let the sale proceed: that holds for
    `resolve_auction` itself, but the screen offers Promote on a listed
    graduate as "keep them", so the API ends the sale.

    Refused with the embargo's 409 while the team is insolvent, because
    promotion starts a salary (#27).
    """

    def post(self, request, rider_id: int):
        team = team_for(request.user)
        if team is None:
            return Response({"detail": "You do not manage a team."}, status=403)

        # Promotion starts a salary, so an insolvent team is refused like any
        # other view that adds cost (#27, economy/README.md). Discard stays
        # open: it adds nothing.
        embargoed = _embargo_response(team)
        if embargoed is not None:
            return embargoed

        at = now()
        try:
            with transaction.atomic():
                promote(team, rider_id, at=at, roster_cap=ROSTER_CAP)
                cancel_open_auctions([rider_id], at=at)
        except (NotYourProspect, SquadRosterFull) as error:
            return Response({"detail": str(error)}, status=409)

        return Response(status=204)


class DiscardSquadRiderView(APIView):
    """Discard one of the caller's squad's riders — a prospect or a graduate
    (#34). POST, like every other action here: the request is an order, not
    a description of a resource that is already gone.

    A rider with an OPEN auction cannot be discarded: the buyer has money on
    the table and the auction will resolve on its own terms. The check is
    injected rather than looked up inside the service, so `riders/` needs no
    knowledge of the auction market (#34's plan, Design decision 8) — the
    same shape `promote`'s `roster_cap` argument takes the cap from the
    caller.
    """

    def post(self, request, rider_id: int):
        team = team_for(request.user)
        if team is None:
            return Response({"detail": "You do not manage a team."}, status=403)

        try:
            discard(team, rider_id, check=_not_listed)
        except TriageError as error:
            return Response({"detail": str(error)}, status=409)

        return Response(status=204)


def _not_listed(rider) -> None:
    """The discard guard: refuse a rider whose auction is still open.

    Raised rather than returned so `discard`'s signature matches `promote`'s
    — a check that returns a verdict can be forgotten by the caller, while
    one that raises cannot be ignored silently.
    """
    if Auction.objects.filter(rider=rider, status=Auction.Status.OPEN).exists():
        raise ProspectListed("Your listing for this rider is still open.")


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
            return Response(FinancesSerializer({
                "balance": 0, "fanbase": 0, "fanbase_change": 0,
                "weekly_wage_bill": 0, "entries": [],
            }).data)

        entries = list(entries_for(team))
        running = 0
        for entry in reversed(entries):            # chronological, oldest first
            running += entry.amount
            entry.balance_after = running

        latest = fanbase_entries_for(team).filter(
            kind=FanbaseEntry.Kind.WEEKLY,
        ).first()            # model ordering is -occurred_at, -pk

        return Response(FinancesSerializer({
            "balance": balance_for(team),
            "fanbase": fanbase_for(team),
            "fanbase_change": latest.delta if latest else 0,
            "weekly_wage_bill": payroll_for(team),
            "entries": entries,
        }).data)


class SolvencyView(APIView):
    """The caller's team against the insolvency ladder (#27): whether it is
    insolvent, the weekly shortfall to close, how much has been cut, and the
    deadline. A user with no team gets the solvent shape with zeros rather than
    a 403, matching FinancesView."""

    def get(self, request):
        team = team_for(request.user)
        if team is None:
            return Response(SolvencySerializer(_solvency_payload(None, 0)).data)

        position = current_position(now())
        trainer_salary, squad_cost = _regular_costs(team)
        status = solvency_status(
            team, position.season, trainer_salary=trainer_salary, squad_cost=squad_cost,
        )
        return Response(SolvencySerializer(
            _solvency_payload(status, team.riders.count())
        ).data)


def _solvency_payload(status: SolvencyStatus | None, roster_size: int) -> dict:
    base = dict(
        insolvent=False, balance=0, shortfall=0, target=0, cut_so_far=0, outgoings=0,
        income=0, strikes=0, paydays_left=None, deadline=None,
    )
    if status is not None:
        base.update(vars(status))
    return {**base, "roster_size": roster_size, "roster_floor": FORCED_SALE_ROSTER_FLOOR}


def _offer_payload(offer) -> dict:
    profile = PROFILES_BY_KEY[offer.profile]
    return {
        "id": offer.pk,
        "sponsor_name": offer.sponsor_name,
        "profile": offer.profile,
        "label": profile.label,
        "blurb": profile.blurb,
        "weekly_base": offer.weekly_base,
        "floor_amount": offer.floor_amount,
        "ceiling_amount": offer.ceiling_amount,
    }


def _contract_payload(contract) -> dict:
    profile = PROFILES_BY_KEY[contract.profile]
    return {
        "sponsor_name": contract.sponsor_name,
        "profile": contract.profile,
        "label": profile.label,
        "blurb": profile.blurb,
        "weekly_base": contract.weekly_base,
        "floor_amount": contract.floor_amount,
        "ceiling_amount": contract.ceiling_amount,
        "signed_at": contract.signed_at,
    }


class SponsorsView(APIView):
    """The caller's own team's sponsorship: the signed contract, or the
    round to choose from.

    No team id in the URL — the team is always the caller's own via
    team_for(), the same pattern as StaffView. A user with no team gets the
    empty shape rather than a 403, matching FinancesView.

    A round is generated lazily here when the team has neither a contract
    nor offers for the current season — ensure_offer_round is idempotent
    (economy/README.md, D8), so this is safe to call on every GET. This is
    what makes a freshly claimed team see offers immediately rather than
    waiting for the next tick, and what covers a team claimed before any
    season has been declared at all (current_position returns state
    "no_season", season=None, and there is nothing to offer yet).
    """

    def get(self, request):
        team = team_for(request.user)
        if team is None:
            return Response(SponsorsSerializer({"contract": None, "offers": []}).data)

        position = current_position(now())
        if position.season is None:
            return Response(SponsorsSerializer({"contract": None, "offers": []}).data)

        contract = active_contract(team, position.season)
        if contract is not None:
            return Response(SponsorsSerializer({
                "contract": _contract_payload(contract), "offers": [],
            }).data)

        ensure_offer_round(team, position.season, at=now())
        offers = offers_for(team, position.season)
        return Response(SponsorsSerializer({
            "contract": None,
            "offers": [_offer_payload(o) for o in offers],
        }).data)


class SignOfferView(APIView):
    """Sign one of the caller's own offers into an active contract.

    409, not 400, for "not available" and "already sponsored": the request
    is well-formed but the world's state refuses it — the same split
    HireTrainerView documents.
    """

    def post(self, request):
        team = team_for(request.user)
        if team is None:
            return Response({"detail": "You do not manage a team."}, status=403)

        serializer = SignOfferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            sign_offer(team, serializer.validated_data["offer_id"], at=now())
        except (OfferNotAvailable, AlreadySponsored) as exc:
            return Response({"detail": str(exc)}, status=409)

        return Response(status=204)
