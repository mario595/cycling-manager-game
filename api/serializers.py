from __future__ import annotations

from rest_framework import serializers

from riders.display import to_display_scale
from riders.models import ENGINE_ATTRIBUTES


class ClockSerializer(serializers.Serializer):
    current = serializers.DateTimeField()


class PositionSerializer(serializers.Serializer):
    state = serializers.CharField()
    season = serializers.IntegerField(allow_null=True)
    week = serializers.IntegerField(allow_null=True)
    week_ends_at = serializers.DateTimeField(allow_null=True)


class CalendarRaceSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    starts_at = serializers.DateTimeField(allow_null=True)
    status = serializers.CharField()
    distance_km = serializers.FloatField()


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
    deliberately absent: the player must not see them."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    speciality = serializers.CharField(source="get_speciality_display")
    nationality = serializers.CharField(source="get_nationality_display")
    age = serializers.IntegerField()
    height_cm = serializers.IntegerField()
    weight_kg = serializers.IntegerField()
    freshness = serializers.SerializerMethodField()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data.update(_display_scale_attributes(instance))
        return data

    def get_freshness(self, instance) -> int:
        return _display_freshness(instance)


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


class MeSerializer(serializers.Serializer):
    authenticated = serializers.BooleanField()
    display_name = serializers.CharField(allow_null=True)
    team = MeTeamSerializer(allow_null=True)


class CourseSegmentSerializer(serializers.Serializer):
    length = serializers.FloatField()
    gradient = serializers.FloatField()


class RaceDetailSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    status = serializers.CharField()
    starts_at = serializers.DateTimeField(allow_null=True)
    distance_km = serializers.FloatField()
    course = CourseSegmentSerializer(many=True)


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
    finished = serializers.BooleanField()


class RaceResultPointsEntrySerializer(serializers.Serializer):
    team = RaceResultTeamSerializer()
    position = serializers.IntegerField(allow_null=True)
    points = serializers.IntegerField()


class RaceResultRaceSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()
    status = serializers.CharField()


class RaceResultsSerializer(serializers.Serializer):
    race = RaceResultRaceSerializer()
    results = RaceResultEntrySerializer(many=True)
    points = RaceResultPointsEntrySerializer(many=True)


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
    """One trainer as the Staff screen needs them: identity and the five
    skills on the 0-10 display scale, never the stored 1-100 — the same
    rule every rider serializer follows (riders/display.py)."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    nationality = serializers.CharField()
    speciality = serializers.CharField()
    skills = serializers.SerializerMethodField()

    def get_skills(self, obj) -> dict[str, int]:
        return _display_scale_attributes(obj)


class StaffSerializer(serializers.Serializer):
    """The Staff screen's whole state: either a hired trainer or the pool.
    Both keys are always present — `trainer` null when the slot is empty,
    `pool` empty when it is filled — so the SPA branches on one payload
    rather than calling two endpoints."""

    trainer = TrainerSerializer(allow_null=True)
    pool = TrainerSerializer(many=True)


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
    to diff (economy/README.md, *Fanbase is derived too*)."""

    balance = serializers.IntegerField()
    fanbase = serializers.IntegerField()
    fanbase_change = serializers.IntegerField()
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
