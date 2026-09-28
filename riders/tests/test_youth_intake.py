from __future__ import annotations

import random
import statistics

from riders.development_squad import LEVELS
from riders.generation import generate_rider
from riders.pricing import strength
from riders.youth_intake import (
    BAND_WEIGHTS,
    INTAKE_AGE_RANGE,
    generate_youth_rider,
    is_intake_week,
)


def test_intake_weeks_are_4_8_12():
    intake_weeks = [n for n in range(1, 13) if is_intake_week(n)]
    assert intake_weeks == [4, 8, 12]


def test_band_weights_cover_every_level():
    assert set(BAND_WEIGHTS.keys()) == set(LEVELS.keys())


def _promising_or_better_share(level: int) -> int:
    # POTENTIAL_BANDS[2:] is "promising" and "gem" — the top two bands.
    return sum(BAND_WEIGHTS[level][2:])


def test_promising_share_rises_strictly_with_level():
    levels = sorted(BAND_WEIGHTS.keys())
    shares = [_promising_or_better_share(level) for level in levels]
    assert shares == sorted(shares)
    assert len(set(shares)) == len(shares)


def test_bottom_two_bands_are_a_majority_at_every_level():
    for level, weights in BAND_WEIGHTS.items():
        assert sum(weights[:2]) > 50


def test_every_band_possible_at_every_level():
    for weights in BAND_WEIGHTS.values():
        assert all(weight > 0 for weight in weights)


def test_youth_age_is_17_to_19(db):
    rng = random.Random(4)
    for _ in range(200):
        rider = generate_youth_rider(1, rng=rng)
        assert INTAKE_AGE_RANGE[0] <= rider.age <= INTAKE_AGE_RANGE[1]


def test_youth_potential_at_least_best_attribute(db):
    rng = random.Random(5)
    for level in BAND_WEIGHTS:
        for _ in range(100):
            rider = generate_youth_rider(level, rng=rng)
            assert rider.potential >= max(
                rider.climb, rider.sprint, rider.flat, rider.resistance, rider.positioning,
            )


def test_youth_far_below_pro_level_on_average(db):
    rng = random.Random(0)
    youth_strengths = [
        strength(generate_youth_rider(1, rng=rng)) for _ in range(500)
    ]
    pro_strengths = [strength(generate_rider(rng=rng)) for _ in range(500)]

    assert statistics.mean(youth_strengths) < statistics.mean(pro_strengths)


def test_elite_mean_potential_above_regional(db):
    rng = random.Random(0)
    regional = [generate_youth_rider(1, rng=rng).potential for _ in range(2000)]
    elite = [generate_youth_rider(3, rng=rng).potential for _ in range(2000)]

    assert statistics.mean(elite) > statistics.mean(regional)
