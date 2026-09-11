from __future__ import annotations

from rest_framework import serializers


class ClockSerializer(serializers.Serializer):
    current = serializers.DateTimeField()


class PositionSerializer(serializers.Serializer):
    state = serializers.CharField()
    season = serializers.IntegerField(allow_null=True)
    week = serializers.IntegerField(allow_null=True)
    week_ends_at = serializers.DateTimeField(allow_null=True)
