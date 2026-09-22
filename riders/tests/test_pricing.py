from __future__ import annotations

import random
import statistics

from riders.generation import generate_rider
from riders.models import Rider
from riders.pricing import (
    SALARY_AT_MIN_STRENGTH,
    weekly_salary_for,
)

#: WEEKLY_WAGE_PER_RIDER duplicated as a literal, not imported: riders/ may
#: not import economy/ in library code (AGENTS.md), and a test importing it
#: would tie this test's pass/fail to economy/'s import graph rather than
#: to the number itself. Keep this in step with economy.models.WEEKLY_WAGE_PER_RIDER.
_WEEKLY_WAGE_PER_RIDER = 1_200


def _rider(**attrs) -> Rider:
    """An in-memory Rider (never saved) — pricing is pure arithmetic over
    the instance, so no DB is needed."""
    defaults = dict(
        name="Rider",
        speciality=Rider.Speciality.ROULEUR,
        age=27,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    defaults.update(attrs)
    return Rider(**defaults)


def test_stronger_rider_costs_more():
    weak = _rider(climb=30, sprint=30, flat=30, resistance=30, positioning=30)
    strong = _rider(climb=80, sprint=80, flat=80, resistance=80, positioning=80)

    assert weekly_salary_for(strong) > weekly_salary_for(weak)


def test_price_reads_speciality_weighting():
    # The load-bearing test for Design decision 3: two riders of different
    # specialities whose attributes each match their own profile equally
    # well must cost the same. A flat mean would price them identically
    # regardless of profile, which would not actually exercise the
    # weighting — this rider is deliberately lopsided so a bug that
    # ignored SPECIALITY_PROFILES and just averaged would produce a
    # different number.
    # CLIMBER and SPRINTER are exact mirrors of each other in
    # SPECIALITY_PROFILES (climb<->sprint and flat<->resistance swapped,
    # positioning equal), so swapping the same two attribute pairs here
    # gives two riders who match their own profile equally well.
    climber = _rider(
        speciality=Rider.Speciality.CLIMBER,
        climb=90, sprint=40, flat=55, resistance=65, positioning=50,
    )
    sprinter = _rider(
        speciality=Rider.Speciality.SPRINTER,
        climb=40, sprint=90, flat=65, resistance=55, positioning=50,
    )

    assert weekly_salary_for(climber) == weekly_salary_for(sprinter)


def test_prime_age_costs_more_than_the_edges():
    prime = _rider(age=27, climb=60, sprint=60, flat=60, resistance=60, positioning=60)
    young = _rider(age=18, climb=60, sprint=60, flat=60, resistance=60, positioning=60)
    old = _rider(age=40, climb=60, sprint=60, flat=60, resistance=60, positioning=60)

    assert weekly_salary_for(prime) > weekly_salary_for(young)
    assert weekly_salary_for(prime) > weekly_salary_for(old)


def test_age_penalty_is_mild():
    # Design decision 4: age must not swing the price more than ~15%.
    prime = _rider(age=27, climb=60, sprint=60, flat=60, resistance=60, positioning=60)
    edge = _rider(age=18, climb=60, sprint=60, flat=60, resistance=60, positioning=60)

    assert weekly_salary_for(edge) >= weekly_salary_for(prime) * 0.8


def test_floor_attributes_still_cost_at_least_the_minimum():
    floor_rider = _rider(climb=1, sprint=1, flat=1, resistance=1, positioning=1)

    assert weekly_salary_for(floor_rider) >= SALARY_AT_MIN_STRENGTH


def test_result_is_a_whole_credit():
    rider = _rider(climb=70, sprint=65, flat=60, resistance=55, positioning=50)

    assert isinstance(weekly_salary_for(rider), int)


def test_generated_roster_spans_roughly_tenfold():
    # Calibration, not correctness: proves Design decision 6 held. Sampled
    # over a real generated population, not the theoretical 1-100 range —
    # generation.QUALITY_SPREAD and _MAX_STARTING_ATTRIBUTE keep riders
    # well under 100 in practice, so a formula tuned against the
    # theoretical range would never show this spread to a player.
    rng = random.Random(20260922)
    riders = [generate_rider(rng=rng) for _ in range(3000)]
    salaries = sorted(weekly_salary_for(r) for r in riders)

    p5 = salaries[int(0.05 * len(salaries))]
    p95 = salaries[int(0.95 * len(salaries))]

    assert 7 <= p95 / p5 <= 13


def test_generated_roster_average_matches_flat_wage():
    # Calibration, not correctness: proves Design decision 7 held. If this
    # drifts, the feature is quietly rebalancing the economy — the spec's
    # Out of scope forbids that.
    rng = random.Random(20260922)
    riders = [generate_rider(rng=rng) for _ in range(3000)]
    salaries = [weekly_salary_for(r) for r in riders]

    mean = statistics.mean(salaries)

    assert abs(mean - _WEEKLY_WAGE_PER_RIDER) / _WEEKLY_WAGE_PER_RIDER <= 0.10


def test_a_linear_interpolation_would_fail_the_spread_check():
    # Sanity check on the calibration test itself (plan's Verification
    # section): a naive linear interpolation between the same floor and
    # ceiling collapses the spread, and this must actually catch that.
    from riders.pricing import SALARY_AT_MAX_STRENGTH, SALARY_AT_MIN_STRENGTH, strength

    def linear_salary(rider) -> int:
        scaled = max(0.0, min(1.0, strength(rider) / 100))
        base = SALARY_AT_MIN_STRENGTH + (SALARY_AT_MAX_STRENGTH - SALARY_AT_MIN_STRENGTH) * scaled
        return max(SALARY_AT_MIN_STRENGTH, round(base / 50) * 50)

    rng = random.Random(20260922)
    riders = [generate_rider(rng=rng) for _ in range(3000)]
    salaries = sorted(linear_salary(r) for r in riders)

    p5 = salaries[int(0.05 * len(salaries))]
    p95 = salaries[int(0.95 * len(salaries))]

    assert not (7 <= p95 / p5 <= 13)
