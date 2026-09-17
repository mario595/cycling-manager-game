from __future__ import annotations

import random

from riders.generation import BUILD_PROFILES, _roll_potential, generate_rider, generate_roster
from riders.models import ENGINE_ATTRIBUTES, Rider
from riders.services import FRESHNESS_MAX


def test_generated_rider_is_valid(db):
    """Clamping test: 200 seeded riders, every one must pass full_clean()."""
    rng = random.Random(1)
    for _ in range(200):
        rider = generate_rider(rng=rng)
        rider.full_clean()


def test_climber_climbs_and_is_light(db):
    rng = random.Random(2)
    climber = generate_rider(speciality=Rider.Speciality.CLIMBER, quality=70, rng=rng)
    sprinter_weight_mean = BUILD_PROFILES[Rider.Speciality.SPRINTER][1]

    best_attribute = max(ENGINE_ATTRIBUTES, key=lambda name: getattr(climber, name))
    assert best_attribute == "climb"
    assert climber.weight_kg < sprinter_weight_mean


def test_generation_is_deterministic():
    first = generate_rider(rng=random.Random(42))
    second = generate_rider(rng=random.Random(42))

    assert first.name == second.name
    assert first.speciality == second.speciality
    assert first.nationality == second.nationality
    assert first.age == second.age
    assert first.potential == second.potential
    for attribute in ENGINE_ATTRIBUTES:
        assert getattr(first, attribute) == getattr(second, attribute)


def test_young_rider_potential_is_above_current():
    rng = random.Random(3)
    for _ in range(100):
        rider = generate_rider(age=21, rng=rng)
        best_attribute = max(getattr(rider, name) for name in ENGINE_ATTRIBUTES)
        assert rider.potential >= best_attribute


def test_potential_at_peak_age_is_above_current():
    """Regression: age < peak_age used to exclude age == peak_age, where
    headroom and shortfall are both 0 and potential collapsed to quality —
    which a high profile-weight roll can push below best_attribute."""
    rng = random.Random(6)
    for _ in range(100):
        quality = rng.randint(1, 95)
        best_attribute = min(100, round(quality * 1.45))
        potential = _roll_potential(quality, best_attribute, age=27, peak_age=27, rng=rng)
        assert potential >= best_attribute


def test_roster_has_a_spread(db):
    rng = random.Random(4)
    roster = generate_roster(12, rng=rng)

    totals = [sum(getattr(r, name) for name in ENGINE_ATTRIBUTES) for r in roster]
    assert max(totals) - min(totals) > 100


def test_roster_size_and_team(db, team):
    roster = generate_roster(12, team=team, rng=random.Random(5))

    assert len(roster) == 12
    assert all(rider.team_id == team.pk for rider in roster)


def test_generated_rider_starts_at_full_freshness(db):
    rider = generate_rider(rng=random.Random(7))

    assert rider.freshness == FRESHNESS_MAX
