from __future__ import annotations

import random
import statistics
from datetime import datetime, timezone as dt_timezone

from riders.development_squad import LEVELS
from riders.generation import generate_rider
from riders.models import DevelopmentSquad, Rider, RiderAttributeSnapshot
from riders.pricing import strength
from riders.youth_intake import (
    BAND_WEIGHTS,
    INTAKE_AGE_RANGE,
    INTAKE_BATCH_SIZE,
    generate_youth_rider,
    is_intake_week,
    run_intake,
)

AT = datetime(2027, 3, 1, tzinfo=dt_timezone.utc)


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


def test_run_intake_adds_batch_to_every_open_squad(team):
    DevelopmentSquad.objects.create(team=team, level=1, opened_at=AT)

    created = run_intake(at=AT, rng=random.Random(6))

    assert created == INTAKE_BATCH_SIZE
    assert Rider.objects.filter(development_squad__team=team).count() == INTAKE_BATCH_SIZE


def test_run_intake_riders_have_no_team_and_carry_intake_at(team):
    squad = DevelopmentSquad.objects.create(team=team, level=1, opened_at=AT)

    run_intake(at=AT, rng=random.Random(7))

    for rider in Rider.objects.filter(development_squad=squad):
        assert rider.team_id is None
        assert rider.intake_at == AT


def test_run_intake_skips_team_without_squad(team):
    created = run_intake(at=AT, rng=random.Random(8))

    assert created == 0


def test_run_intake_twice_same_at_is_idempotent(team):
    DevelopmentSquad.objects.create(team=team, level=1, opened_at=AT)

    first = run_intake(at=AT, rng=random.Random(9))
    second = run_intake(at=AT, rng=random.Random(10))

    assert first == INTAKE_BATCH_SIZE
    assert second == 0
    assert Rider.objects.filter(development_squad__team=team).count() == INTAKE_BATCH_SIZE


def test_run_intake_writes_baseline_snapshots(team):
    squad = DevelopmentSquad.objects.create(team=team, level=1, opened_at=AT)

    run_intake(at=AT, rng=random.Random(11))

    riders = Rider.objects.filter(development_squad=squad)
    assert riders.count() == INTAKE_BATCH_SIZE
    for rider in riders:
        assert RiderAttributeSnapshot.objects.filter(rider=rider, week=None).exists()
