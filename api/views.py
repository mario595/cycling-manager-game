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

from competitions.scoring import POINTS_BY_POSITION, points_for, prize_for
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
from economy.sponsors import PROFILES_BY_KEY
from racing.models import SQUAD_SIZE, MarkerCrossing, Race, RaceLog, RaceSquadRider
from racing.services import SquadError, set_squad, suggested_squad
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
)
# Aliased, not shadowed: staff.services.InsufficientFunds is imported
# unaliased above, and the two are unrelated classes. Catching the wrong one
# turns a 409 the player should see into a 500.
from riders.development_squad import InsufficientFunds as SquadInsufficientFunds
from riders.models import ENGINE_ATTRIBUTES, DevelopmentSquad, Rider
from riders.pricing import strength
from riders.youth_intake import INTAKE_BATCH_SIZE, INTAKE_INTERVAL_WEEKS, is_intake_week
from schedule.models import SEASON_WEEKS, Week
from schedule.services import current_position, weeks_opened_between
from staff.pricing import hire_fee
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
    AuctionAlreadyExists,
    AuctionNotOpen,
    BidTooLow,
    InsufficientFunds as TransferInsufficientFunds,
    RiderNotAvailable,
    RiderNotOnRoster,
    RosterFull,
    SelfBid,
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


class PlaceBidView(APIView):
    """Place a bid on an open auction. Balance checked here (Design
    decision 8) against economy.services.balance_for BEFORE calling
    transfers.services.place_bid — no charge happens yet, so there is no
    injected charge callback on this path, unlike sign_free_agent."""

    def post(self, request, auction_id):
        team = team_for(request.user)
        if team is None:
            return Response({"detail": "You do not manage a team."}, status=403)

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
            "markers": [
                {
                    "id": m.pk,
                    "kind": m.kind,
                    "name": m.name,
                    "distance": m.distance,
                }
                for m in race.markers.all()  # model ordering: distance, pk
            ],
            # Whether the SPA can offer a Watch race. A row with a file is
            # enough: stat'ing the file here would be a network round trip
            # per detail view once logs move to object storage, and a log
            # that has gone missing surfaces on the replay screen itself
            # (D5).
            "has_replay": RaceLog.objects.filter(race=race).exclude(file="").exists(),
        }
        return Response(RaceDetailSerializer(payload).data)


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
        "finished": result.finish_time is not None,
    }


def _crossing_payload(crossing, team_by_rider) -> dict:
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
    }


#: How many crossings per marker the results screen shows — D11. The full
#: order stays in the database for the features above the markers.
MARKER_PLACES_SHOWN = 3


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
        markers_payload = [
            {
                "id": m.pk,
                "kind": m.kind,
                "name": m.name,
                "distance": m.distance,
                "crossings": [
                    _crossing_payload(c, team_by_rider)
                    for c in m.crossings.all()  # model ordering: marker, position
                ],
            }
            for m in markers.all()  # model ordering: distance, pk
        ]
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
            "results": [_result_row(r, team_by_rider.get(r.rider_id)) for r in results],
            "points": points_payload,
            "markers": markers_payload,
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


def _next_intake(at) -> dict | None:
    """{season, week} of the first declared Week after `at` that is an
    intake week, or None when no such week is declared yet — a season not
    yet loaded past this point, or no season at all. At most a few dozen
    Week rows exist, so a Python-side is_intake_week filter over one ordered
    query is simpler than reimplementing `% INTAKE_INTERVAL_WEEKS` in SQL,
    and it keeps the rule in the one place riders.youth_intake owns it."""
    for week in Week.objects.select_related("season").filter(
        starts_at__gt=at,
    ).order_by("starts_at"):
        if is_intake_week(week.number):
            return {"season": week.season.number, "week": week.number}
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
                    "action": status.action,
                    # Why a locked level is locked, and null for every other
                    # action. Server-owned for the same reason the 409
                    # details are: it is a statement about the game, and the
                    # screen has no business re-deriving it.
                    "requires": status.note,
                }
            )

        at = now()
        if squad is not None:
            riders = sorted(
                Rider.objects.filter(development_squad=squad),
                key=strength, reverse=True,
            )
            intake = {
                "every_weeks": INTAKE_INTERVAL_WEEKS,
                "batch_size": INTAKE_BATCH_SIZE,
                "next": _next_intake(at),
            }
            latest_intake_at = _latest_intake_at(at)
        else:
            riders = []
            intake = None
            latest_intake_at = None

        return Response(DevelopmentSquadSerializer({
            "level": current_level,
            "levels": levels,
            "balance": balance_for(team),
            "riders": riders,
            "intake": intake,
        }, context={"latest_intake_at": latest_intake_at}).data)


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
    """
    def post(self, request):
        team = team_for(request.user)
        if team is None:
            return Response({"detail": "You do not manage a team."}, status=403)

        if not close_squad(team, at=now()):
            return Response(
                {"detail": "Your team has no development squad."}, status=409
            )

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
