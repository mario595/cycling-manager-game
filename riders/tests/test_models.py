from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

from riders.models import Rider


def test_rider_has_speciality_and_hidden_traits(rider):
    assert rider.speciality == Rider.Speciality.ROULEUR
    assert rider.nationality == Rider.Nationality.SPAIN
    assert rider.height_cm == 178
    assert rider.weight_kg == 70
    assert rider.age == 25
    assert rider.potential == 70
    assert rider.peak_age == 27
    assert rider.decline_rate == 50
    assert rider.injury_proneness == 50
    assert rider.training_affinity == {}


def test_growth_debt_defaults_to_an_empty_dict(rider):
    assert rider.growth_debt == {}


def test_rider_speciality_rejects_value_outside_choices(rider):
    rider.speciality = "time-trialist"
    with pytest.raises(ValidationError):
        rider.full_clean()


def test_weekly_salary_defaults_to_the_flat_wage(rider):
    assert rider.weekly_salary == 1200


def test_weekly_salary_rejects_zero(rider):
    rider.weekly_salary = 0
    with pytest.raises(ValidationError):
        rider.full_clean()
