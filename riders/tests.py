from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

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
        role=Rider.Role.LEADER,
        climb=94,
        sprint=30,
        flat=40,
        resistance=80,
        positioning=52,
    )


def test_rider_has_speciality_and_hidden_traits(rider):
    assert rider.speciality == Rider.Speciality.ROULEUR
    assert rider.height_cm == 178
    assert rider.weight_kg == 70
    assert rider.age == 25
    assert rider.potential == 70
    assert rider.peak_age == 27
    assert rider.decline_rate == 50
    assert rider.injury_proneness == 50
    assert rider.training_affinity == {}


def test_rider_speciality_rejects_value_outside_choices(rider):
    rider.speciality = "time-trialist"
    with pytest.raises(ValidationError):
        rider.full_clean()
