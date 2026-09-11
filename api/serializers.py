from __future__ import annotations

from rest_framework import serializers

from world.models import GameClock, TickRun


class GameClockSerializer(serializers.ModelSerializer):
    last_tick = serializers.SerializerMethodField()

    class Meta:
        model = GameClock
        fields = ["current", "catch_up_hours", "last_tick"]

    def get_last_tick(self, obj: GameClock) -> str | None:
        latest = TickRun.objects.filter(finished_at__isnull=False).first()
        return latest.finished_at if latest else None
