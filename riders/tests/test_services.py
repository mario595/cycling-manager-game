from __future__ import annotations

import pytest

from riders.generation import SPECIALITY_PROFILES
from riders.models import ENGINE_ATTRIBUTES, Rider
from riders.services import (
    MAX_ATTRIBUTE,
    MIN_ATTRIBUTE,
    _settle,
    advance_ages,
    apply_weekly_growth,
    attribute_ceilings,
    weekly_deltas,
)


def make_rider(**overrides) -> Rider:
    defaults = dict(
        name="Test Rider",
        speciality=Rider.Speciality.CLIMBER,
        age=20,
        potential=80,
        peak_age=27,
        decline_rate=50,
        climb=40,
        sprint=40,
        flat=40,
        resistance=40,
        positioning=40,
    )
    defaults.update(overrides)
    return Rider(**defaults)


def test_a_climbers_climb_ceiling_exceeds_their_sprint_ceiling():
    rider = make_rider(speciality=Rider.Speciality.CLIMBER, potential=80)

    ceilings = attribute_ceilings(rider)

    assert ceilings["climb"] > ceilings["sprint"]


def test_ceilings_scale_potential_by_speciality_profile():
    rider = make_rider(speciality=Rider.Speciality.CLIMBER, potential=80)
    profile = SPECIALITY_PROFILES[Rider.Speciality.CLIMBER]
    mean_weight = sum(profile.values()) / len(profile)

    ceilings = attribute_ceilings(rider)

    assert ceilings["climb"] == pytest.approx(80 * (profile["climb"] / mean_weight))
    assert ceilings["sprint"] == pytest.approx(80 * (profile["sprint"] / mean_weight))


def test_a_young_rider_below_potential_grows():
    rider = make_rider(age=20, peak_age=27, climb=40, potential=90)

    deltas = weekly_deltas(rider, weeks=1)

    assert deltas["climb"] > 0


def test_a_rider_past_peak_age_declines():
    rider = make_rider(age=30, peak_age=27, decline_rate=50)

    deltas = weekly_deltas(rider, weeks=1)

    for name in ENGINE_ATTRIBUTES:
        assert deltas[name] < 0


def test_decline_accelerates_with_years_past_peak():
    one_year_past = make_rider(age=28, peak_age=27, decline_rate=50)
    three_years_past = make_rider(age=30, peak_age=27, decline_rate=50)

    delta_one = weekly_deltas(one_year_past, weeks=1)["climb"]
    delta_three = weekly_deltas(three_years_past, weeks=1)["climb"]

    assert abs(delta_three) > abs(delta_one)


def test_a_higher_decline_rate_falls_faster():
    slow = make_rider(age=30, peak_age=27, decline_rate=10)
    fast = make_rider(age=30, peak_age=27, decline_rate=90)

    delta_slow = weekly_deltas(slow, weeks=1)["climb"]
    delta_fast = weekly_deltas(fast, weeks=1)["climb"]

    assert abs(delta_fast) > abs(delta_slow)


def test_a_rider_at_their_ceiling_below_peak_does_not_move():
    rider = make_rider(age=20, peak_age=27, potential=1, speciality=Rider.Speciality.ROULEUR)
    # Force every attribute to already sit at or above its ceiling.
    ceilings = attribute_ceilings(rider)
    for name in ENGINE_ATTRIBUTES:
        setattr(rider, name, max(1, round(ceilings[name]) + 5))

    deltas = weekly_deltas(rider, weeks=1)

    for name in ENGINE_ATTRIBUTES:
        assert deltas[name] == 0.0


def test_four_weeks_of_growth_equals_four_applications_of_one_week():
    rider = make_rider(age=20, peak_age=27, potential=90, climb=40)

    batched = weekly_deltas(rider, weeks=4)["climb"]

    # Apply one week's delta four times by hand, mutating a copy's climb
    # each time, to prove the closed-form batch calculation is exact
    # rather than an approximation.
    iterative_rider = make_rider(age=20, peak_age=27, potential=90, climb=40)
    for _ in range(4):
        step = weekly_deltas(iterative_rider, weeks=1)["climb"]
        iterative_rider.climb = iterative_rider.climb + step

    iterative_total = iterative_rider.climb - 40

    assert batched == pytest.approx(iterative_total, abs=1e-9)


def test_fractional_growth_accumulates_across_weeks_instead_of_being_lost(db):
    # A weekly delta under 1.0 must still add up over many weeks rather
    # than being rounded to 0 (truncated) or to 1 (rounded) every time.
    # `flat` is close to its own ceiling here while `climb` still has a
    # wide gap, so its weekly delta is the small, sub-1.0 one to watch.
    rider = Rider.objects.create(
        name="Young Climber",
        speciality=Rider.Speciality.CLIMBER,
        age=26,
        peak_age=27,
        potential=70,
        decline_rate=50,
        climb=60,
        sprint=40,
        flat=52,
        resistance=40,
        positioning=40,
    )
    weekly_flat_delta = weekly_deltas(rider, weeks=1)["flat"]
    assert 0 < weekly_flat_delta < 1

    for _ in range(7):
        apply_weekly_growth(weeks=1)
        rider.refresh_from_db()
    # Seven weeks of ~0.14/week accumulates to just under 1.0 of debt —
    # the attribute has not moved yet, proving the fraction was not
    # discarded on any single week.
    assert rider.flat == 52

    apply_weekly_growth(weeks=1)
    rider.refresh_from_db()
    # The eighth week tips accumulated debt over 1.0 and the stored
    # integer attribute finally moves — proving it was carried, not lost.
    assert rider.flat == 53


def test_attributes_never_leave_the_1_100_range(db):
    rider = Rider.objects.create(
        name="Ancient Rider",
        speciality=Rider.Speciality.CLIMBER,
        age=40,
        peak_age=22,
        potential=100,
        decline_rate=100,
        climb=1,
        sprint=1,
        flat=1,
        resistance=1,
        positioning=1,
    )

    apply_weekly_growth(weeks=500)
    rider.refresh_from_db()

    for name in ENGINE_ATTRIBUTES:
        assert MIN_ATTRIBUTE <= getattr(rider, name) <= MAX_ATTRIBUTE


def test_debt_does_not_accumulate_once_an_attribute_is_clamped():
    new_value, remainder = _settle(current=MIN_ATTRIBUTE, debt=-0.9, delta=-0.9)

    assert new_value == MIN_ATTRIBUTE
    assert remainder == 0.0


def test_ageing_advances_every_rider_including_free_agents(db):
    rostered = Rider.objects.create(name="Rostered", age=25, climb=1, sprint=1, flat=1, resistance=1, positioning=1)
    free_agent = Rider.objects.create(name="Free Agent", team=None, age=25, climb=1, sprint=1, flat=1, resistance=1, positioning=1)

    changed = advance_ages()

    rostered.refresh_from_db()
    free_agent.refresh_from_db()
    assert changed == 2
    assert rostered.age == 26
    assert free_agent.age == 26


def test_ageing_stops_at_the_model_maximum(db):
    rider = Rider.objects.create(name="Veteran", age=40, climb=1, sprint=1, flat=1, resistance=1, positioning=1)

    advance_ages()
    rider.refresh_from_db()

    assert rider.age == 40
