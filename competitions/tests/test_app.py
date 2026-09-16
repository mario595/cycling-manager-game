from __future__ import annotations

import pytest
from django.apps import apps
from django.db import IntegrityError, transaction

from competitions.models import RacePoints


def test_app_is_installed():
    assert apps.is_installed("competitions")


def test_race_points_unique_per_team_per_race(race, make_team):
    team = make_team("ALP")
    RacePoints.objects.create(race=race, team=team, position=1, points=20)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            RacePoints.objects.create(race=race, team=team, position=2, points=15)
