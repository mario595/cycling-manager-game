from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.management import call_command

from racing.models import Race
from riders.models import Rider
from schedule.models import Season
from teams.models import Team
from world.services import now


@pytest.fixture
def team(db) -> Team:
    return Team.objects.create(name="Team Alpha", code="ALP", primary_colour="#FF0000")


@pytest.fixture
def four_riders(db, team) -> list[Rider]:
    return [
        Rider.objects.create(
            name=f"Rider {i}",
            team=team,
            climb=60,
            sprint=60,
            flat=60,
            resistance=60,
            positioning=60,
        )
        for i in range(4)
    ]


def test_tick_command_runs_and_reports(db, four_riders, capsys):
    race = Race.objects.create(
        name="Due Race",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=now() - timedelta(hours=1),
        status=Race.Status.SCHEDULED,
    )

    call_command("tick")

    race.refresh_from_db()
    assert race.status == Race.Status.FINISHED
    out = capsys.readouterr().out
    assert "races started 1, finished 1" in out
    assert "capped=False" in out


def test_tick_summary_reports_season_transitions(db, capsys):
    Season.objects.create(number=1, starts_at=now() - timedelta(hours=1))

    call_command("tick")

    out = capsys.readouterr().out
    assert "seasons opened 1, closed 0" in out
