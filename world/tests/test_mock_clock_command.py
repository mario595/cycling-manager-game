from __future__ import annotations

from datetime import timedelta, timezone as dt_timezone

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import override_settings
from django.utils.dateparse import parse_datetime

from racing.models import Race
from world.services import now


def test_set_moves_the_clock(db):
    call_command("mock_clock", "set", "2027-03-01T09:00")

    assert now() == parse_datetime("2027-03-01T09:00").replace(tzinfo=dt_timezone.utc)


def test_advance_to_next_moves_to_the_next_due_race(db):
    due_at = now() + timedelta(hours=3)
    Race.objects.create(
        name="Next Up", course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=due_at, status=Race.Status.SCHEDULED,
    )

    call_command("mock_clock", "advance", "--to-next")

    assert now() == due_at


@pytest.mark.parametrize(
    "value, expected",
    [
        ("1d", timedelta(days=1)),
        ("6h", timedelta(hours=6)),
        ("1d6h", timedelta(days=1, hours=6)),
        ("30m", timedelta(minutes=30)),
    ],
)
def test_advance_by_parses_duration_strings(db, value, expected):
    before = now()

    call_command("mock_clock", "advance", "--by", value)

    assert now() == before + expected


def test_refuses_to_rewind_past_a_finished_race_without_force(db):
    finished_at = now()
    Race.objects.create(
        name="Already Done",
        course=[{"length": 500.0, "gradient": 0.0}],
        status=Race.Status.FINISHED,
        finished_at=finished_at,
    )

    earlier = (finished_at - timedelta(days=1)).isoformat()
    with pytest.raises(CommandError):
        call_command("mock_clock", "set", earlier)

    call_command("mock_clock", "set", earlier, "--force")
    assert now() == parse_datetime(earlier)


@override_settings(GAME_CLOCK_CLASS="world.clocks.RealClock")
def test_raises_when_real_clock_is_active(db):
    with pytest.raises(CommandError):
        call_command("mock_clock", "set", "2027-03-01T09:00")
