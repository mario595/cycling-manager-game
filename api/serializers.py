from __future__ import annotations

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from feedback.models import Report
from riders.display import to_display_scale
from riders.models import ENGINE_ATTRIBUTES, DevelopmentSquad
from riders.services import is_due_to_retire
from schedule.services import current_position
from staff.pricing import hire_fee, weekly_salary
from transfers.pricing import market_value_for, signing_fee_for
from transfers.services import release_cost_for
from world.services import now


class ClockSerializer(serializers.Serializer):
    current = serializers.DateTimeField()


class PositionSerializer(serializers.Serializer):
    state = serializers.CharField()
    season = serializers.IntegerField(allow_null=True)
    week = serializers.IntegerField(allow_null=True)
    week_ends_at = serializers.DateTimeField(allow_null=True)


class StageRaceRefSerializer(serializers.Serializer):
    """A race's stage-race context, when it has one — the calendar entry
    that groups its stages, and the results/squad payloads' pointer back
    to it. `None` (the field is omitted by allow_null on the parent) for a
    one-day race — see racing/README.md, *Stage races*."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    stage_number = serializers.IntegerField()
    stage_count = serializers.IntegerField()


class CalendarRaceSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    starts_at = serializers.DateTimeField(allow_null=True)
    status = serializers.CharField()
    distance_km = serializers.FloatField()
    stage_race = StageRaceRefSerializer(allow_null=True)


class CalendarWeekSerializer(serializers.Serializer):
    number = serializers.IntegerField()
    starts_at = serializers.DateTimeField()
    races = CalendarRaceSerializer(many=True)


class CalendarSerializer(serializers.Serializer):
    state = serializers.CharField()
    season = serializers.IntegerField(allow_null=True)
    current_week = serializers.IntegerField(allow_null=True)
    weeks = CalendarWeekSerializer(many=True)


def _display_scale_attributes(obj) -> dict[str, int]:
    """The five engine attributes on the 0-10 scale the player sees, never
    the stored 1-100 — see riders/display.py. `obj` is a dict (the squad
    endpoint's candidate payload) or a Rider instance (the roster endpoint);
    both support the same attribute lookup via getattr, since dict has no
    attribute access but Rider does, so branch on the object's type once
    here rather than in every caller."""
    get = (lambda name: obj[name]) if isinstance(obj, dict) else (lambda name: getattr(obj, name))
    return {name: to_display_scale(get(name)) for name in ENGINE_ATTRIBUTES}


def _display_freshness(obj) -> int:
    """Freshness on the same 0-10 scale as the attributes, for the same two
    object shapes as _display_scale_attributes — dicts from the squad
    endpoint, Rider instances from the roster endpoint."""
    if isinstance(obj, dict):
        return to_display_scale(obj["freshness"])
    return to_display_scale(obj.freshness)


def _in_season(context: dict) -> bool:
    """Whether a season is running now, computed once per response and
    cached on the shared serializer context (#42).

    The cache is the point: DRF gives every nested and `many` serializer the
    root's context dict, so a thirty-rider roster pays for one lookup rather
    than thirty. It also means a future view that forgets to pass the flag
    through still gets it, unlike a hand-threaded argument.
    """
    if "in_season" not in context:
        context["in_season"] = current_position(now()).state == "in_season"
    return context["in_season"]


class SquadRiderSerializer(serializers.Serializer):
    """One rider as the squad screen needs them: identity, speciality,
    age, the five engine attributes on the 0-10 display scale (never the
    stored 1-100 — see riders/display.py) and freshness mapped through the
    same scale, for the manager to compare on, plus whether they are in the
    squad and leading it. The recovery rate is deliberately not included."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    speciality = serializers.CharField()
    age = serializers.IntegerField()
    selected = serializers.BooleanField()
    is_leader = serializers.BooleanField()
    freshness = serializers.SerializerMethodField()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data.update(_display_scale_attributes(instance))
        return data

    def get_freshness(self, instance) -> int:
        return _display_freshness(instance)


class RiderSerializer(serializers.Serializer):
    """One rider as the roster screen needs them. Attributes and freshness
    are the 0-10 display scale, never the stored 1-100 — see
    riders/display.py. Hidden traits (potential, peak age, decline rate,
    injury proneness, training affinity) and the recovery rate are
    deliberately absent: the player must not see them. `final_season` is the
    one visible consequence of the hidden retirement age (#42) — the age
    itself is never shipped, only whether this is the rider's last season."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    speciality = serializers.CharField(source="get_speciality_display")
    nationality = serializers.CharField(source="get_nationality_display")
    age = serializers.IntegerField()
    height_cm = serializers.IntegerField()
    weight_kg = serializers.IntegerField()
    freshness = serializers.SerializerMethodField()
    weekly_salary = serializers.IntegerField()
    market_value = serializers.SerializerMethodField()
    release_cost = serializers.SerializerMethodField()
    final_season = serializers.SerializerMethodField()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data.update(_display_scale_attributes(instance))
        return data

    def get_freshness(self, instance) -> int:
        return _display_freshness(instance)

    def get_market_value(self, instance) -> int:
        return market_value_for(instance)

    def get_release_cost(self, instance) -> int | None:
        """What releasing this rider would charge right now, via
        transfers.services.release_cost_for — 0 within the claim cooldown,
        severance otherwise. Needs the requesting team and the in-season
        weeks opened since its claim, which share a DRF `context` with this
        serializer (RiderListView builds it, and DRF propagates `context` to
        every nested serializer). `None` — not a crash — when a future call
        site forgets the context."""
        team = self.context.get("team")
        weeks_opened = self.context.get("weeks_opened")
        if team is None or weeks_opened is None:
            return None
        return release_cost_for(team, instance, weeks_opened=weeks_opened)

    def get_final_season(self, instance) -> bool:
        """Whether this rider retires when the running season closes (#42).

        The marker is derived, not stored: it lasts exactly the one season
        the rider retires in, so it disappears between seasons and returns
        for whoever is still in the window when the next one opens.
        """
        return _in_season(self.context) and is_due_to_retire(instance)


class SalaryChangeSerializer(serializers.Serializer):
    """One rider's wage movement at a season close. Whole credits, never
    the display scale — this is money (riders/README.md, *Salary*)."""

    rider_id = serializers.IntegerField()
    rider_name = serializers.CharField()
    from_value = serializers.IntegerField(source="from")
    to_value = serializers.IntegerField(source="to")


class SalaryReviewSerializer(serializers.Serializer):
    """Schema only: the shape RosterSerializer.get_salary_review builds."""

    season_number = serializers.IntegerField()
    payroll_before = serializers.IntegerField()
    payroll_after = serializers.IntegerField()
    changes = SalaryChangeSerializer(many=True)


class RosterSerializer(serializers.Serializer):
    """The caller's own team's roster: every rider plus the squad's total
    market value, so the roster screen's header total and its per-rider
    figures can never disagree (#31), and the latest post-season salary
    review when one exists — `salary_review` null otherwise, so the SPA
    branches on one response (the same whole-payload rule
    TrainingSerializer follows)."""

    riders = RiderSerializer(many=True)
    squad_value = serializers.IntegerField()
    salary_review = serializers.SerializerMethodField()

    @extend_schema_field(SalaryReviewSerializer(allow_null=True))
    def get_salary_review(self, obj):
        report = obj["salary_review"]
        if report is None:
            return None
        return {
            "season_number": report.season.number,
            "payroll_before": report.payroll_before,
            "payroll_after": report.payroll_after,
            "changes": SalaryChangeSerializer(report.changes, many=True).data,
        }


class FreeAgentSerializer(RiderSerializer):
    """A free agent as the transfer market needs them: everything
    RiderSerializer already ships (the same visible fields a manager's own
    roster shows), plus one figure this screen adds — the signing fee.
    `release_cost` is inherited and ships as `null` — these riders are on
    nobody's roster, so the free-agent context carries no team for the
    RosterSerializer to read; the frontend documents and expects exactly
    that."""

    signing_fee = serializers.SerializerMethodField()

    def get_signing_fee(self, instance) -> int:
        return signing_fee_for(instance)


class FreeAgentPoolSerializer(serializers.Serializer):
    """The transfer market's whole state, the same both-keys-always-present
    shape StaffSerializer uses: the pool of free agents plus the caller's
    balance, so the SPA can disable a Sign it cannot afford."""

    riders = FreeAgentSerializer(many=True)
    balance = serializers.IntegerField()


class SignFreeAgentSerializer(serializers.Serializer):
    rider_id = serializers.IntegerField()


class ReleaseRiderSerializer(serializers.Serializer):
    rider_id = serializers.IntegerField()


class BidSerializer(serializers.Serializer):
    """One bid in an auction's full history — which team placed it, when,
    and for how much. Bidding is not anonymous (spec, *Rules and edge
    cases*): every listing shows its whole history, newest/highest first,
    not just the current leader."""

    team_name = serializers.CharField()
    amount = serializers.IntegerField()
    placed_at = serializers.DateTimeField()


class AuctionSerializer(serializers.Serializer):
    """One live auction as the market screen shows it: rider, price, time
    left, and its full bid history. `min_next_bid`, `is_own_listing` and
    `bids` are computed by the view, not derived here, since none is a
    plain attribute of an Auction row. `min_next_bid` is `current_price`
    itself while `bids` is empty — the reserve is a valid opening bid
    (transfers.services.place_bid) — and `current_price + min_increment`
    once a bid exists."""

    id = serializers.IntegerField()
    rider = RiderSerializer()
    current_price = serializers.IntegerField()
    min_next_bid = serializers.IntegerField()
    deadline = serializers.DateTimeField()
    is_own_listing = serializers.BooleanField()
    forced = serializers.BooleanField()
    bids = BidSerializer(many=True)


class AuctionMarketSerializer(serializers.Serializer):
    """Same both-keys-always-present shape FreeAgentPoolSerializer uses."""

    auctions = AuctionSerializer(many=True)
    balance = serializers.IntegerField()


class ListForAuctionSerializer(serializers.Serializer):
    rider_id = serializers.IntegerField()


class PlaceBidSerializer(serializers.Serializer):
    amount = serializers.IntegerField(min_value=1)


class MyBidStatusSerializer(serializers.Serializer):
    """One row for "auctions I've bid on" — spec item 8, outbid
    visibility. `is_high_bidder` tells the frontend whether to show
    "you're winning" vs "outbid"."""

    auction_id = serializers.IntegerField()
    rider_name = serializers.CharField()
    my_last_bid = serializers.IntegerField()
    current_price = serializers.IntegerField()
    is_high_bidder = serializers.BooleanField()
    deadline = serializers.DateTimeField()


class SquadRaceStageSerializer(serializers.Serializer):
    """A squad's stage-race context: enough for the screen to explain WHY
    it's read-only from stage 2 on — see specs/archive/stage-races.md, Decisions
    taken (squad chosen once, for stage 1)."""

    name = serializers.CharField()
    stage_number = serializers.IntegerField()


class SquadSerializer(serializers.Serializer):
    race = serializers.IntegerField()
    race_name = serializers.CharField()
    race_status = serializers.CharField()
    starts_at = serializers.DateTimeField(allow_null=True)
    distance_km = serializers.FloatField()
    team = serializers.IntegerField()
    team_name = serializers.CharField()
    editable = serializers.BooleanField()
    saved = serializers.BooleanField()  # False when this is a suggestion
    squad_size = serializers.IntegerField()
    candidates = SquadRiderSerializer(many=True)
    stage_race = SquadRaceStageSerializer(allow_null=True)


class SquadWriteSerializer(serializers.Serializer):
    rider_ids = serializers.ListField(child=serializers.IntegerField())
    leader_id = serializers.IntegerField()


class MeTeamSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    code = serializers.CharField()


class ClaimTeamSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=100)
    code = serializers.CharField(min_length=3, max_length=3)

    def validate_code(self, value):
        return value.upper()


class LostTeamSerializer(serializers.Serializer):
    spell = serializers.IntegerField()
    name = serializers.CharField()
    code = serializers.CharField()
    reason = serializers.CharField()
    ended_at = serializers.DateTimeField()


class MeSerializer(serializers.Serializer):
    authenticated = serializers.BooleanField()
    display_name = serializers.CharField(allow_null=True)
    team = MeTeamSerializer(allow_null=True)
    lost_team = LostTeamSerializer(allow_null=True)


class CourseSegmentSerializer(serializers.Serializer):
    length = serializers.FloatField()
    gradient = serializers.FloatField()


class RacePayoutEntrySerializer(serializers.Serializer):
    position = serializers.IntegerField()
    points = serializers.IntegerField()
    prize = serializers.IntegerField()


class RaceMarkerSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    kind = serializers.CharField()
    name = serializers.CharField()
    distance = serializers.FloatField()
    weight = serializers.CharField(allow_null=True)
    category = serializers.CharField(allow_null=True)
    points = serializers.ListField(child=serializers.IntegerField(), allow_null=True)


class RaceDetailStageSerializer(serializers.Serializer):
    """One stage as listed in a race detail's stage_race block, for the
    stage strip that links between a tour's stages."""

    id = serializers.IntegerField()
    stage_number = serializers.IntegerField()
    starts_at = serializers.DateTimeField(allow_null=True)
    status = serializers.CharField()


class RaceDetailStageRaceSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    stage_number = serializers.IntegerField()
    stage_count = serializers.IntegerField()
    stages = RaceDetailStageSerializer(many=True)


class RaceDetailSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    status = serializers.CharField()
    starts_at = serializers.DateTimeField(allow_null=True)
    distance_km = serializers.FloatField()
    course = CourseSegmentSerializer(many=True)
    payout = RacePayoutEntrySerializer(many=True)
    gc_payout = RacePayoutEntrySerializer(many=True)
    markers = RaceMarkerSerializer(many=True)
    has_replay = serializers.BooleanField()
    stage_race = RaceDetailStageRaceSerializer(allow_null=True)


class RaceResultTeamSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    code = serializers.CharField()


class RaceResultRiderSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()


class RaceResultEntrySerializer(serializers.Serializer):
    position = serializers.IntegerField()
    rider = RaceResultRiderSerializer()
    team = RaceResultTeamSerializer(allow_null=True)
    finish_time = serializers.FloatField(allow_null=True)
    group_time = serializers.FloatField(allow_null=True)
    finished = serializers.BooleanField()


class RaceResultPointsEntrySerializer(serializers.Serializer):
    team = RaceResultTeamSerializer()
    position = serializers.IntegerField(allow_null=True)
    finish_points = serializers.IntegerField()
    sprint_points = serializers.IntegerField()
    mountain_points = serializers.IntegerField()
    points = serializers.IntegerField()
    prize = serializers.IntegerField()


class RaceResultRaceSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    status = serializers.CharField()
    stage_race = StageRaceRefSerializer(allow_null=True)


class RaceMarkerCrossingSerializer(serializers.Serializer):
    position = serializers.IntegerField()
    rider = RaceResultRiderSerializer()
    team = RaceResultTeamSerializer(allow_null=True)
    points = serializers.IntegerField(allow_null=True)


class RaceMarkerResultSerializer(RaceMarkerSerializer):
    crossings = RaceMarkerCrossingSerializer(many=True)


class GCStandingEntrySerializer(serializers.Serializer):
    position = serializers.IntegerField()
    rider = RaceResultRiderSerializer()
    team = RaceResultTeamSerializer(allow_null=True)
    gc_time = serializers.FloatField()
    gap = serializers.FloatField()  # 0.0 for the leader


class GCPointsEntrySerializer(serializers.Serializer):
    team = RaceResultTeamSerializer()
    position = serializers.IntegerField()
    points = serializers.IntegerField()
    prize = serializers.IntegerField()


class GCSerializer(serializers.Serializer):
    """A stage race's general classification as of the results screen's own
    race — see racing.services.general_classification, D6. `final` is true
    once the whole stage race has completed; `points` is only populated
    then, matching when the GC award is actually made (D11)."""

    after_stage = serializers.IntegerField()
    final = serializers.BooleanField()
    standings = GCStandingEntrySerializer(many=True)
    points = GCPointsEntrySerializer(many=True)


class RaceResultsSerializer(serializers.Serializer):
    race = RaceResultRaceSerializer()
    results = RaceResultEntrySerializer(many=True)
    points = RaceResultPointsEntrySerializer(many=True)
    markers = RaceMarkerResultSerializer(many=True)
    gc = GCSerializer(allow_null=True)


class AttributeSnapshotSerializer(serializers.Serializer):
    """One point on the attribute-history chart — already display-scale
    (0-10) values, never re-mapped through to_display_scale (riders/README.md,
    *Attribute history*). `season`/`week` are both null for the baseline."""

    season = serializers.IntegerField(allow_null=True)
    week = serializers.IntegerField(allow_null=True)
    climb = serializers.IntegerField()
    sprint = serializers.IntegerField()
    flat = serializers.IntegerField()
    resistance = serializers.IntegerField()
    positioning = serializers.IntegerField()


class CurrentWeekSerializer(serializers.Serializer):
    season = serializers.IntegerField()
    week = serializers.IntegerField()


class RetiredSerializer(serializers.Serializer):
    season = serializers.IntegerField(allow_null=True)
    week = serializers.IntegerField(allow_null=True)


class RiderProfileRaceInfoSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    starts_at = serializers.DateTimeField(allow_null=True)


class RiderRaceSerializer(serializers.Serializer):
    """One race-history row: the team is the one the rider raced for
    (D4), never their current team. No points field — race points are a
    team award, not an individual one (D5)."""

    race = RiderProfileRaceInfoSerializer()
    team = RaceResultTeamSerializer(allow_null=True)
    position = serializers.IntegerField()
    finish_time = serializers.FloatField(allow_null=True)
    winner_time = serializers.FloatField(allow_null=True)
    finished = serializers.BooleanField()


class CareerSerializer(serializers.Serializer):
    """Totals derived in Python from the same race list the page shows
    (D6). No points field (D5)."""

    starts = serializers.IntegerField()
    wins = serializers.IntegerField()
    podiums = serializers.IntegerField()
    top_tens = serializers.IntegerField()
    dnfs = serializers.IntegerField()


class RiderProfileSerializer(RiderSerializer):
    """One rider's full profile: every RiderSerializer key unchanged (D3),
    plus the current team, where the world is now, the attribute-history
    chart's points, the race history and the career totals — all read from
    `self.context["profile"]`, the dict api.rider_profile.rider_profile
    builds, so RiderSerializer's own instance handling stays untouched."""

    team = serializers.SerializerMethodField()
    current_week = serializers.SerializerMethodField()
    retired = serializers.SerializerMethodField()
    attribute_history = serializers.SerializerMethodField()
    races = serializers.SerializerMethodField()
    career = serializers.SerializerMethodField()
    development_squad = serializers.SerializerMethodField()

    def get_team(self, instance) -> dict | None:
        team = self.context["profile"]["team"]
        return RaceResultTeamSerializer(team).data if team is not None else None

    def get_development_squad(self, instance) -> dict | None:
        """The owning team's {id, name, code} while this rider sits in that
        team's development squad (#33), or null — the same shape get_team
        uses, since a squad rider's profile names the team by way of the
        squad, not a direct roster link."""
        squad_team = self.context["profile"]["development_squad"]
        return RaceResultTeamSerializer(squad_team).data if squad_team is not None else None

    def get_current_week(self, instance) -> dict | None:
        current_week = self.context["profile"]["current_week"]
        return CurrentWeekSerializer(current_week).data if current_week is not None else None

    def get_retired(self, instance) -> dict | None:
        retired = self.context["profile"]["retired"]
        return RetiredSerializer(retired).data if retired is not None else None

    def get_attribute_history(self, instance) -> list[dict]:
        return AttributeSnapshotSerializer(self.context["profile"]["attribute_history"], many=True).data

    def get_races(self, instance) -> list[dict]:
        return RiderRaceSerializer(self.context["profile"]["races"], many=True).data

    def get_career(self, instance) -> dict:
        return CareerSerializer(self.context["profile"]["career"]).data


class StandingsTeamSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    code = serializers.CharField()


class StandingsEntrySerializer(serializers.Serializer):
    rank = serializers.IntegerField()
    team = StandingsTeamSerializer()
    points = serializers.IntegerField()


class StandingsSerializer(serializers.Serializer):
    state = serializers.CharField()
    season = serializers.IntegerField(allow_null=True)
    standings = StandingsEntrySerializer(many=True)


class TrainerSerializer(serializers.Serializer):
    """One trainer as the Staff screen needs them: identity, the five
    skills on the 0-10 display scale, never the stored 1-100 — the same
    rule every rider serializer follows (riders/display.py) — and the two
    prices derived from those skills (staff/pricing.py), so the card can
    show what hiring costs before the manager commits."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    nationality = serializers.CharField()
    speciality = serializers.CharField()
    skills = serializers.SerializerMethodField()
    hire_fee = serializers.SerializerMethodField()
    weekly_salary = serializers.SerializerMethodField()

    def get_skills(self, obj) -> dict[str, int]:
        return _display_scale_attributes(obj)

    def get_hire_fee(self, obj) -> int:
        return hire_fee(obj)

    def get_weekly_salary(self, obj) -> int:
        return weekly_salary(obj)


class StaffSerializer(serializers.Serializer):
    """The Staff screen's whole state: either a hired trainer or the pool,
    plus the team's balance so the SPA can disable a hire it cannot afford.
    Both trainer keys are always present — `trainer` null when the slot is
    empty, `pool` empty when it is filled — so the SPA branches on one
    payload rather than calling two endpoints."""

    trainer = TrainerSerializer(allow_null=True)
    pool = TrainerSerializer(many=True)
    balance = serializers.IntegerField()


class HireTrainerSerializer(serializers.Serializer):
    trainer_id = serializers.IntegerField()


class TrainingChangeSerializer(serializers.Serializer):
    """One rider's visible movement at a rollover. Display scale only, and
    deliberately no hidden traits — the report carries exactly what the
    player can already see (riders/README.md)."""

    rider_id = serializers.IntegerField()
    rider_name = serializers.CharField()
    attribute = serializers.CharField()
    from_value = serializers.IntegerField(source="from")
    to_value = serializers.IntegerField(source="to")


class TrainingWeekSerializer(serializers.Serializer):
    """Schema only: the shape TrainingSerializer.get_last_week builds."""

    attribute = serializers.CharField()
    changes = TrainingChangeSerializer(many=True)


class TrainingSerializer(serializers.Serializer):
    """The Training screen's whole state in one payload, the same shape
    rule StaffSerializer follows: every key always present, so the SPA
    branches on one response rather than calling three endpoints.

    `last_week` is null when no rollover report exists yet; otherwise it
    carries the focus that was applied and the display-scale changes (an
    empty `changes` list is normal)."""

    has_trainer = serializers.BooleanField()
    focus = serializers.CharField(allow_null=True)
    options = serializers.ListField(child=serializers.CharField())
    last_week = serializers.SerializerMethodField()

    @extend_schema_field(TrainingWeekSerializer(allow_null=True))
    def get_last_week(self, obj):
        report = obj["last_week"]
        if report is None:
            return None
        return {
            "attribute": report.attribute,
            "changes": TrainingChangeSerializer(report.changes, many=True).data,
        }


class TrainingFocusSerializer(serializers.Serializer):
    """The PUT body: one of the five attribute names. The ChoiceField makes
    an unknown value a 400 before the view is reached."""

    attribute = serializers.ChoiceField(choices=ENGINE_ATTRIBUTES)


class LedgerEntrySerializer(serializers.Serializer):
    """One ledger entry as the Finances screen needs it: what happened,
    when, how much, and the balance after it — spec rule 11. `kind` is the
    machine name (starting_balance/wages/takeover); the SPA renders the
    label. `rider_count` is set on wage entries only — null elsewhere.
    `id` exists so the SPA can key React's list on a stable unique value
    rather than on a (kind, occurred_at, amount) triplet."""

    id = serializers.IntegerField()
    kind = serializers.CharField()
    description = serializers.CharField()
    amount = serializers.IntegerField()
    occurred_at = serializers.DateTimeField(allow_null=True)
    rider_count = serializers.IntegerField(allow_null=True)
    balance_after = serializers.IntegerField()


class FinancesSerializer(serializers.Serializer):
    """The Finances screen's whole state: the running balance, the team's
    fanbase and how it moved this week, and the full history, newest first,
    each entry carrying the balance after it was written — the view computes
    `balance_after`; see economy/README.md.

    `fanbase_change` is the most recent `weekly` fanbase row's delta, or 0
    when none exists yet — the player sees the change, not two raw numbers
    to diff (economy/README.md, *Fanbase is derived too*).

    `weekly_wage_bill` is the team's current payroll — the sum of its
    riders' actual weekly_salary (#25), from economy.services.payroll_for.
    Not read from the ledger's own wage entry: a manager can buy or sell a
    rider mid-week, and the bill should say what leaves *next* payday, not
    what left last time."""

    balance = serializers.IntegerField()
    fanbase = serializers.IntegerField()
    fanbase_change = serializers.IntegerField()
    weekly_wage_bill = serializers.IntegerField()
    entries = LedgerEntrySerializer(many=True)


class SponsorOfferSerializer(serializers.Serializer):
    """One unsigned offer as the Sponsors screen needs it: the four money
    figures plus the profile's player-facing character, already resolved
    from PROFILES_BY_KEY — the SPA renders label/blurb verbatim, it does
    not know about profiles as a concept."""

    id = serializers.IntegerField()
    sponsor_name = serializers.CharField()
    profile = serializers.CharField()
    label = serializers.CharField()
    blurb = serializers.CharField()
    weekly_base = serializers.IntegerField()
    floor_amount = serializers.IntegerField()
    ceiling_amount = serializers.IntegerField()


class SponsorContractSerializer(serializers.Serializer):
    """The signed contract, same shape as SponsorOfferSerializer plus
    `signed_at` — there is no `id` the SPA needs to key on since only one
    contract is ever shown."""

    sponsor_name = serializers.CharField()
    profile = serializers.CharField()
    label = serializers.CharField()
    blurb = serializers.CharField()
    weekly_base = serializers.IntegerField()
    floor_amount = serializers.IntegerField()
    ceiling_amount = serializers.IntegerField()
    signed_at = serializers.DateTimeField()


class SponsorsSerializer(serializers.Serializer):
    """The Sponsors screen's whole state: either a signed contract or the
    round to choose from — the same both-keys-always-present shape
    StaffSerializer uses, so the SPA branches on one payload."""

    contract = SponsorContractSerializer(allow_null=True)
    offers = SponsorOfferSerializer(many=True)


class SignOfferSerializer(serializers.Serializer):
    offer_id = serializers.IntegerField()


class DevelopmentSquadRiderSerializer(serializers.Serializer):
    """One development squad rider as the squad screen shows them: identity,
    speciality, age, the five attributes on the 0-10 display scale, when
    they arrived and whether they are from the latest batch (#33), plus how
    long their spell has left, what they have gained since they arrived, and
    what promoting them would cost in wages (#34).

    Deliberately **not** a RiderSerializer subclass, unlike
    RiderProfileSerializer above — subclassing would inherit weekly_salary,
    market_value, release_cost and final_season, none of which apply to a
    rider who draws no wage and isn't in any market (riders/README.md,
    *Youth intake*). `promotion_salary` is the one wage figure that does
    apply: what they would draw *after* being promoted, not what they draw
    now.

    **`weeks_left`, `change` and `promotion_salary` come from context maps
    built once in the view**, never from a per-rider query: the screen asks
    for one squad, so a query per rider would be a query per prospect for
    data the view already has.
    """

    id = serializers.IntegerField()
    name = serializers.CharField()
    speciality = serializers.CharField(source="get_speciality_display")
    nationality = serializers.CharField(source="get_nationality_display")
    age = serializers.IntegerField()
    arrived = serializers.SerializerMethodField()
    is_new = serializers.SerializerMethodField()
    weeks_left = serializers.SerializerMethodField()
    change = serializers.SerializerMethodField()
    promotion_salary = serializers.SerializerMethodField()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data.update(_display_scale_attributes(instance))
        return data

    def get_arrived(self, instance) -> dict:
        position = current_position(instance.intake_at)
        if position.state == "no_season":
            return {"season": None, "week": None}
        if position.state == "off_season":
            return {"season": position.season.number, "week": None}
        return {"season": position.season.number, "week": position.week.number}

    def get_is_new(self, instance) -> bool:
        latest_intake_at = self.context.get("latest_intake_at")
        return latest_intake_at is not None and instance.intake_at == latest_intake_at

    def get_weeks_left(self, instance) -> int:
        return self.context["weeks_left"][instance.pk]

    def get_change(self, instance) -> dict | None:
        return _change_since_arrival(instance, self.context.get("baselines"))

    def get_promotion_salary(self, instance) -> int:
        return self.context["promotion_salaries"][instance.pk]


class DevelopmentSquadGraduateSerializer(DevelopmentSquadRiderSerializer):
    """A rider who has finished their spell and is waiting to be decided
    about (#34).

    Adds the two figures that only make sense for someone the squad could
    sell or sign: what they are worth on the market, and whether they are
    already listed. `weeks_left` is the *decision window* here, not the rest
    of a spell — the count down to being released to the free-agent pool,
    after which they are the market's to sign rather than the squad's to
    manage."""

    market_value = serializers.SerializerMethodField()
    listed = serializers.SerializerMethodField()

    def get_weeks_left(self, instance) -> int:
        # The decision window, not the rest of a spell: the count down to
        # being released to the free-agent pool, after which they are the
        # market's to sign rather than the squad's to manage.
        return self.context["graduate_weeks_left"][instance.pk]

    def get_market_value(self, instance) -> int:
        return self.context["market_values"][instance.pk]

    def get_listed(self, instance) -> bool:
        return self.context["listed"].get(instance.pk, False)


def _change_since_arrival(instance, baselines) -> dict | None:
    """Current displayed value minus the rider's baseline snapshot: the five
    attribute keys to signed integers, or None with no baseline (#34,
    Design decision 15).

    Taken from the display scale on both sides, never from the stored 1-100
    values — a raw difference would show movement the player cannot see on
    the bars, which is exactly the number this field exists to replace.
    """
    baseline = (baselines or {}).get(instance.pk)
    if baseline is None:
        return None
    return {
        name: to_display_scale(getattr(instance, name)) - getattr(baseline, name)
        for name in ENGINE_ATTRIBUTES
    }


class DevelopmentSquadNextIntakeSerializer(serializers.Serializer):
    """The next intake week and how many of its batch would be lost.

    Its own serializer rather than a reuse of `RetiredSerializer`, which grew
    a third field here and would otherwise carry a `state` the squad screen
    has no use for (#34)."""

    season = serializers.IntegerField(allow_null=True)
    week = serializers.IntegerField(allow_null=True)
    arrivals_at_risk = serializers.IntegerField()


class DevelopmentSquadIntakeSerializer(serializers.Serializer):
    """How often a squad's riders arrive, and when the next batch is due —
    the squad screen's own words for the cadence, never a percentage and
    never a promise about a single batch (riders/README.md, *Youth
    intake*)."""

    every_weeks = serializers.IntegerField()
    batch_size = serializers.IntegerField()
    # {season, week, arrivals_at_risk}, the same shape RetiredSerializer gives
    # a nullable season position — null when no further intake week is
    # declared in the calendar yet. `arrivals_at_risk` is how many of that
    # batch would be turned away if nothing changed before it arrives, so the
    # warning can be given before the week rather than after (#34, Design
    # decision 14). It is a projection: promoting or discarding a prospect
    # changes it.
    next = DevelopmentSquadNextIntakeSerializer(allow_null=True)


class DevelopmentSquadLevelSerializer(serializers.Serializer):
    """One level as the screen needs to show it: what moving onto it costs,
    what running it costs, what that adds up to over a season, and what the
    team can do about it right now.

    `action` is the ladder rule as the server sees it — `open`, `upgrade`,
    `current` or `locked` — and the SPA renders it rather than deriving it, so
    a locked card and a 409 come from the same call. `requires` names the
    level that has to be open first, and is null for every other action.

    `fee` is what entering this level costs, and it is the same number the
    ledger is debited when the move is made: the entry level's fee opens the
    squad, and each level above charges its own in full to upgrade into it.
    There is no "current" level's fee, because there is no move onto the level
    already held.

    `places` is how many prospects the level can hold, and it is what
    decides how much of each intake batch arrives (#34) — shown on every
    card so the cost and the capacity of a rung are read together.
    """

    level = serializers.IntegerField()
    name = serializers.CharField()
    weekly_cost = serializers.IntegerField()
    season_cost = serializers.IntegerField()
    fee = serializers.IntegerField()
    places = serializers.IntegerField()
    action = serializers.ChoiceField(
        choices=["open", "upgrade", "current", "locked"]
    )
    requires = serializers.CharField(allow_null=True)


class DevelopmentSquadSerializer(serializers.Serializer):
    """The Development squad screen's whole state: which level is open (null
    when closed), every level with its prices, the balance, so the SPA can
    disable an action the team cannot afford without a second round trip —
    the same both-keys-always-present shape StaffSerializer uses — plus the
    squad's own riders and the intake cadence (#33). `riders` is empty and
    `intake` still present while the squad is open with nothing arrived yet;
    the view sends [] for both rider keys and null for `intake` while the
    squad is closed, since a closed squad has no riders and nothing due.

    **The squad's own state at the top level** (#34): `places` (the current
    level's, null while closed), `in_squad`, and `roster_count` with
    `roster_cap` — the last two so the screen can disable Promote without
    provoking a 409, and so "your roster is full" is a fact on the screen
    rather than a rejection the player has to provoke first. `riders` is the
    in-squad prospects and `graduates` those who have finished their spell
    and are waiting to be promoted, listed or discarded."""

    level = serializers.IntegerField(allow_null=True)
    levels = DevelopmentSquadLevelSerializer(many=True)
    balance = serializers.IntegerField()
    places = serializers.IntegerField(allow_null=True)
    in_squad = serializers.IntegerField()
    roster_count = serializers.IntegerField()
    roster_cap = serializers.IntegerField()
    riders = DevelopmentSquadRiderSerializer(many=True)
    graduates = DevelopmentSquadGraduateSerializer(many=True)
    intake = DevelopmentSquadIntakeSerializer(allow_null=True)


class DevelopmentSquadLevelChoiceSerializer(serializers.Serializer):
    """The POST body for opening or changing level. The ChoiceField makes an
    unknown level a 400 before the view is reached, which is why the views
    still guard with UnknownLevel rather than relying on it."""

    level = serializers.ChoiceField(choices=DevelopmentSquad.Level.choices)


class SolvencySerializer(serializers.Serializer):
    """Where a team stands against the insolvency ladder (#27).

    `shortfall` is the live weekly gap between regular outgoings and regular
    income; `target` is what it was at the last payday, so `cut_so_far` is the
    progress since. `paydays_left` is null when the live shortfall is zero (the
    target is met for now) and `deadline` is null when the weeks it falls in are
    not declared yet — the SPA then says "in N paydays".
    """

    insolvent = serializers.BooleanField()
    balance = serializers.IntegerField()
    shortfall = serializers.IntegerField()
    target = serializers.IntegerField()
    cut_so_far = serializers.IntegerField()
    outgoings = serializers.IntegerField()
    income = serializers.IntegerField()
    strikes = serializers.IntegerField()
    paydays_left = serializers.IntegerField(allow_null=True)
    deadline = serializers.DateTimeField(allow_null=True)
    roster_size = serializers.IntegerField()
    roster_floor = serializers.IntegerField()


class ReportSerializer(serializers.Serializer):
    """A beta tester's report, as its own reporter sees it (#131). Deliberately
    no `triage_note`: that is staff-only — see feedback/README.md, *Triage*.
    The team is the snapshot taken when it was sent, never the author's
    current team."""

    id = serializers.IntegerField()
    category = serializers.CharField()
    text = serializers.CharField()
    location = serializers.CharField()
    team_name = serializers.CharField()
    season_number = serializers.IntegerField(allow_null=True)
    week_number = serializers.IntegerField(allow_null=True)
    game_time = serializers.DateTimeField()
    created_at = serializers.DateTimeField()
    status = serializers.CharField()
    github_issue_url = serializers.CharField()


class ReportCreateSerializer(serializers.Serializer):
    """What a reporter sends. Everything else on a report is worked out by
    the server. Over-long text is refused rather than cut."""

    category = serializers.ChoiceField(choices=Report.Category.choices)
    text = serializers.CharField(max_length=4000)
    location = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
