from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from racing.models import Race
from riders.models import Rider
from teams.models import Team
from world.models import GameClock


@pytest.fixture
def team(db) -> Team:
    return Team.objects.create(name="Team Alpha", code="ALP", primary_colour="#FF0000")


@pytest.fixture
def four_riders(db, team) -> list[Rider]:
    return [
        Rider.objects.create(
            name=f"Rider {i}",
            team=team,
            role=Rider.Role.LEADER if i == 0 else Rider.Role.SUPPORT,
            climb=60,
            sprint=60,
            flat=60,
            resistance=60,
            positioning=60,
        )
        for i in range(4)
    ]


def test_tick_advances_clock(db, four_riders):
    clock = GameClock.load()
    before = clock.current

    call_command("tick")

    clock.refresh_from_db()
    assert clock.current > before


def test_day_flag_processes_races_within_the_day(db, four_riders):
    clock = GameClock.load()
    race = Race.objects.create(
        name="Day Race",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=clock.current + timedelta(hours=2),
        status=Race.Status.SCHEDULED,
    )

    call_command("tick", "--day")

    race.refresh_from_db()
    assert race.status == Race.Status.FINISHED


def test_to_next_and_day_together_is_an_error(db):
    with pytest.raises(CommandError):
        call_command("tick", "--to-next", "--day")
