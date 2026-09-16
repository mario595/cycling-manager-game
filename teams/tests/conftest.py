from __future__ import annotations

import pytest

from riders.models import Rider
from teams.models import Team


@pytest.fixture
def team(db) -> Team:
    return Team.objects.create(name="Team Alpha", code="ALP", primary_colour="#FF0000")


@pytest.fixture
def rider(db, team) -> Rider:
    return Rider.objects.create(
        name="Climber One",
        team=team,
        climb=94,
        sprint=30,
        flat=40,
        resistance=80,
        positioning=52,
    )
