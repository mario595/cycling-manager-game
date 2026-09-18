from __future__ import annotations

import pytest

from teams.models import Team


@pytest.fixture
def team(db) -> Team:
    return Team.objects.create(name="Team Alpha", code="ALP", primary_colour="#FF0000")


@pytest.fixture
def other_team(db) -> Team:
    return Team.objects.create(name="Team Beta", code="BET", primary_colour="#0000FF")