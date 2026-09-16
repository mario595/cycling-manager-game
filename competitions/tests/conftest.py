from __future__ import annotations

import pytest

from racing.models import Race
from riders.models import Rider
from teams.models import Team


@pytest.fixture
def race(db) -> Race:
    return Race.objects.create(
        name="Test Stage",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.FINISHED,
    )


@pytest.fixture
def make_team(db):
    """Factory: make_team("ALP") -> Team named "Team ALP" with that code."""
    def _make(code: str) -> Team:
        return Team.objects.create(name=f"Team {code}", code=code)
    return _make


@pytest.fixture
def make_rider(db):
    """Factory for a rider on a team; engine attributes are irrelevant to
    scoring, so they default to a flat 50."""
    def _make(name: str, team: Team) -> Rider:
        return Rider.objects.create(
            name=name, team=team,
            climb=50, sprint=50, flat=50, resistance=50, positioning=50,
        )
    return _make


@pytest.fixture
def make_result(db):
    """Factory for a RaceResult row: make_result(race, rider, position,
    finish_time=1000.0). finish_time=None means the rider did not finish."""
    def _make(race: Race, rider: Rider, position: int, finish_time: float | None = 1000.0):
        from racing.models import RaceResult
        return RaceResult.objects.create(
            race=race, rider=rider, position=position, finish_time=finish_time,
        )
    return _make
