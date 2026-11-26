from __future__ import annotations

import random
import statistics

from riders.generation import generate_rider
from riders.models import Rider
from riders.pricing import weekly_salary_for
from transfers.pricing import (
    career_horizon,
    market_value_for,
    min_increment_for,
    reserve_price_for,
    severance_fee_for,
    signing_fee_for,
)


def _rider(**attrs) -> Rider:
    """An in-memory Rider (never saved) — pricing is pure arithmetic over
    the instance, so no DB is needed. Mirrors riders/tests/test_pricing.py's
    helper."""
    defaults = dict(
        name="Rider",
        speciality=Rider.Speciality.ROULEUR,
        age=27,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    defaults.update(attrs)
    return Rider(**defaults)


def test_stronger_rider_is_worth_more():
    weak = _rider(climb=30, sprint=30, flat=30, resistance=30, positioning=30)
    strong = _rider(climb=80, sprint=80, flat=80, resistance=80, positioning=80)

    assert market_value_for(strong) > market_value_for(weak)


def test_value_reads_speciality_weighting():
    # Same load-bearing pair as riders/tests/test_pricing.py's speciality
    # test: CLIMBER and SPRINTER are exact mirrors in SPECIALITY_PROFILES,
    # so swapping the matching attribute pairs gives two riders who match
    # their own profile equally well and must be worth the same.
    climber = _rider(
        speciality=Rider.Speciality.CLIMBER,
        climb=90, sprint=40, flat=55, resistance=65, positioning=50,
    )
    sprinter = _rider(
        speciality=Rider.Speciality.SPRINTER,
        climb=40, sprint=90, flat=65, resistance=55, positioning=50,
    )

    assert market_value_for(climber) == market_value_for(sprinter)


def test_younger_rider_is_worth_more_at_equal_ability():
    # Load-bearing for D2/D3: with riders.pricing.age_multiplier (1.0 for
    # 24-32, penalised below 24), a 22-year-old would be *cheaper* than a
    # 30-year-old of equal ability. Value must invert that.
    younger = _rider(age=22, climb=60, sprint=60, flat=60, resistance=60, positioning=60)
    older = _rider(age=30, climb=60, sprint=60, flat=60, resistance=60, positioning=60)

    assert market_value_for(younger) > market_value_for(older)


def test_value_falls_monotonically_with_age():
    ages = [23, 28, 33, 38]
    values = [
        market_value_for(_rider(age=age, climb=60, sprint=60, flat=60, resistance=60, positioning=60))
        for age in ages
    ]

    assert values == sorted(values, reverse=True)
    assert len(set(values)) == len(values)


def test_declined_veteran_is_worth_very_little():
    old_and_weak = _rider(
        age=39, climb=1, sprint=1, flat=1, resistance=1, positioning=1,
    )

    value = market_value_for(old_and_weak)

    assert 0 <= value < market_value_for(_rider())


def test_result_is_a_whole_credit():
    rider = _rider(climb=70, sprint=65, flat=60, resistance=55, positioning=50)

    assert isinstance(market_value_for(rider), int)


def test_no_hidden_trait_is_read():
    # D9: two riders identical on every visible field but different on
    # every hidden one must be worth the same.
    visible = dict(
        speciality=Rider.Speciality.PUNCHEUR,
        age=25,
        climb=72, sprint=58, flat=64, resistance=61, positioning=55,
    )
    guarded = _rider(
        **visible,
        potential=90, peak_age=29, decline_rate=10,
        injury_proneness=80, training_affinity={"climb": 0.9},
        recovery_rate=90, growth_debt={"climb": 5.0},
    )
    unguarded = _rider(
        **visible,
        potential=20, peak_age=20, decline_rate=90,
        injury_proneness=5, training_affinity={"climb": 0.1},
        recovery_rate=10, growth_debt={"climb": 0.0},
    )

    assert market_value_for(guarded) == market_value_for(unguarded)


def test_career_horizon_is_flat_at_and_below_peak():
    assert career_horizon(17) == career_horizon(18) == career_horizon(23) == 1.0


def test_signing_fee_is_60_percent_of_value():
    rider = _rider(climb=70, sprint=65, flat=60, resistance=55, positioning=50)

    fee = signing_fee_for(rider)

    # The same nearest-1000 rounding market_value_for itself uses
    # (Design decision 3 — no second rounding convention for fees).
    assert fee == 1000 * round(0.60 * market_value_for(rider) / 1000)
    assert fee > 0


def test_severance_fee_is_30_percent_of_value():
    rider = _rider(climb=70, sprint=65, flat=60, resistance=55, positioning=50)

    fee = severance_fee_for(rider)

    assert fee == 1000 * round(0.30 * market_value_for(rider) / 1000)
    assert fee > 0


def test_career_horizon_never_exceeds_its_bounds():
    for age in range(17, 41):
        assert 0.15 <= career_horizon(age) <= 1.0


#: A twelve-week season (schedule/README.md), the "roughly a season's
#: wages" anchor the spec's D4 promises. Not imported from schedule/:
#: transfers/ may only import riders/ (AGENTS.md), and a test importing it
#: would tie this test's pass/fail to schedule/'s import graph rather than
#: to the number itself.
_WEEKS_PER_SEASON = 12


def test_average_value_is_about_one_season_of_wages():
    # Calibration, not correctness: proves Design decision 4 held. Sampled
    # over a real generated population, like riders/tests/test_pricing.py's
    # own calibration tests, not reasoned about from the theoretical range.
    rng = random.Random(20260922)
    riders = [generate_rider(rng=rng) for _ in range(3000)]

    mean_salary = statistics.mean(weekly_salary_for(r) for r in riders)
    mean_value = statistics.mean(market_value_for(r) for r in riders)

    target = mean_salary * _WEEKS_PER_SEASON
    assert abs(mean_value - target) / target <= 0.15


def test_reserve_price_is_half_signing_fee_rate():
    rider = _rider(climb=70, sprint=65, flat=60, resistance=55, positioning=50)

    reserve = reserve_price_for(rider)

    assert reserve == 1000 * round(0.50 * market_value_for(rider) / 1000)
    assert reserve > 0


def test_min_increment_is_fraction_of_reserve():
    rider = _rider(climb=70, sprint=65, flat=60, resistance=55, positioning=50)
    reserve = reserve_price_for(rider)

    increment = min_increment_for(reserve)

    assert increment == 1000 * round(0.05 * reserve / 1000)

    # Mutating the rider in-memory afterwards must not move an increment
    # already derived from a frozen reserve_price (Design decision 5) —
    # min_increment_for takes the number, not the rider.
    rider.climb = 99
    rider.sprint = 99
    assert min_increment_for(reserve) == increment


def test_generated_roster_value_spans_wider_than_salary():
    # Proves the age skew actually widens the spread rather than just
    # rescaling salary's — if this ties or loses to salary's spread, D2/D3
    # are not doing anything.
    rng = random.Random(20260922)
    riders = [generate_rider(rng=rng) for _ in range(3000)]

    salaries = sorted(weekly_salary_for(r) for r in riders)
    values = sorted(market_value_for(r) for r in riders)

    def spread(sorted_values):
        p5 = sorted_values[int(0.05 * len(sorted_values))]
        p95 = sorted_values[int(0.95 * len(sorted_values))]
        return p95 / p5

    assert spread(values) > spread(salaries)


def test_market_value_scales_with_the_field_factor():
    # #166: value, and with it every fee, is priced against the field.
    rider = _rider(climb=70)

    assert market_value_for(rider, 1.0) == market_value_for(rider)
    assert market_value_for(rider, 1.1) > market_value_for(rider)
    assert signing_fee_for(rider, 0.9) < signing_fee_for(rider)
