from __future__ import annotations

from rest_framework import serializers


class ClockSerializer(serializers.Serializer):
    current = serializers.DateTimeField()
