from __future__ import annotations

import pytest
from django.apps import apps
from django.db import IntegrityError, transaction

from competitions.models import RacePoints
from racing.models import Race
from teams.models import Team


def test_app_is_installed():
    assert apps.is_installed("competitions")


@pytest.fixture
def team(db) -> Team:
    return Team.objects.create(name="Team Alpha", code="ALP")


@pytest.fixture
def race(db) -> Race:
    return Race.objects.create(
        name="Test Stage",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.FINISHED,
    )


def test_race_points_unique_per_team_per_race(race, team):
    RacePoints.objects.create(race=race, team=team, position=1, points=20)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            RacePoints.objects.create(race=race, team=team, position=2, points=15)
