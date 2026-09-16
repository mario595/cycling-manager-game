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


class SquadRiderSerializer(serializers.Serializer):
    """One rider as the squad screen needs them: identity, speciality and
    age, the five engine attributes on the 0-10 display scale (never the
    stored 1-100 — see riders/display.py) for the manager to compare on, and
    whether they are in the squad and leading it."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    speciality = serializers.CharField()
    age = serializers.IntegerField()
    selected = serializers.BooleanField()
    is_leader = serializers.BooleanField()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data.update(_display_scale_attributes(instance))
        return data


class RiderSerializer(serializers.Serializer):
    """One rider as the roster screen needs them. Attributes are the 0-10
    display scale, never the stored 1-100 — see riders/display.py. Hidden
    traits (potential, peak age, decline rate, injury proneness, training
    affinity) are deliberately absent: the player must not see them."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    speciality = serializers.CharField(source="get_speciality_display")
    nationality = serializers.CharField(source="get_nationality_display")
    age = serializers.IntegerField()
    height_cm = serializers.IntegerField()
    weight_kg = serializers.IntegerField()

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data.update(_display_scale_attributes(instance))
        return data


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


class MeSerializer(serializers.Serializer):
    authenticated = serializers.BooleanField()
    display_name = serializers.CharField(allow_null=True)
    team = MeTeamSerializer(allow_null=True)


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
    position = serializers.IntegerField()
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
