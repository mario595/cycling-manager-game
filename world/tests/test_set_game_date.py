from __future__ import annotations

from datetime import timedelta, timezone as dt_timezone

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils.dateparse import parse_datetime

from racing.models import Race
from world.models import GameClock


def test_sets_clock(db):
    call_command("set_game_date", "2027-03-01T09:00")

    clock = GameClock.load()
    assert clock.current == parse_datetime("2027-03-01T09:00").replace(tzinfo=dt_timezone.utc)


def test_refuses_to_rewind_past_a_finished_race_without_force(db):
    clock = GameClock.load()
    finished_at = clock.current
    Race.objects.create(
        name="Already Done",
        course=[{"length": 500.0, "gradient": 0.0}],
        status=Race.Status.FINISHED,
        finished_at=finished_at,
    )

    earlier = (finished_at - timedelta(days=1)).isoformat()
    with pytest.raises(CommandError):
        call_command("set_game_date", earlier)

    call_command("set_game_date", earlier, "--force")
    clock.refresh_from_db()
    assert clock.current == parse_datetime(earlier)
