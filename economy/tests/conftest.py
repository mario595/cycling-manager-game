from __future__ import annotations

import pytest

from racing.models import Race
from teams.models import Team


@pytest.fixture
def team(db) -> Team:
    return Team.objects.create(name="Team Alpha", code="ALP", primary_colour="#FF0000")


@pytest.fixture
def other_team(db) -> Team:
    return Team.objects.create(name="Team Beta", code="BET", primary_colour="#0000FF")


@pytest.fixture
def race(db) -> Race:
    return Race.objects.create(
        name="Test Stage",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.FINISHED,
    )