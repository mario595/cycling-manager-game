from __future__ import annotations

from rest_framework import serializers


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


class SquadRiderSerializer(serializers.Serializer):
    """One rider as the squad screen needs them: identity, the five engine
    attributes for the manager to compare on, and whether they are in the
    squad and leading it."""

    id = serializers.IntegerField()
    name = serializers.CharField()
    role = serializers.CharField()  # the rider's default, not the squad's
    climb = serializers.IntegerField()
    sprint = serializers.IntegerField()
    flat = serializers.IntegerField()
    resistance = serializers.IntegerField()
    positioning = serializers.IntegerField()
    selected = serializers.BooleanField()
    is_leader = serializers.BooleanField()


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
