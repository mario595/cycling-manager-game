from __future__ import annotations

import random
import statistics
from datetime import datetime, timedelta, timezone as dt_timezone

from riders.development_squad import LEVELS
from riders.generation import generate_rider
from riders.models import DevelopmentSquad, Rider, RiderAttributeSnapshot
from riders.pricing import strength
from riders.youth_triage import graduates, in_squad
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

    result = run_intake(at=AT, rng=random.Random(6))

    assert result.created == INTAKE_BATCH_SIZE
    assert result.turned_away == 0
    assert Rider.objects.filter(development_squad__team=team).count() == INTAKE_BATCH_SIZE


def test_run_intake_riders_have_no_team_and_carry_intake_at(team):
    squad = DevelopmentSquad.objects.create(team=team, level=1, opened_at=AT)

    run_intake(at=AT, rng=random.Random(7))

    for rider in Rider.objects.filter(development_squad=squad):
        assert rider.team_id is None
        assert rider.intake_at == AT


def test_run_intake_skips_team_without_squad(team):
    assert run_intake(at=AT, rng=random.Random(8)).created == 0


def test_run_intake_twice_same_at_is_idempotent(team):
    DevelopmentSquad.objects.create(team=team, level=1, opened_at=AT)

    first = run_intake(at=AT, rng=random.Random(9))
    second = run_intake(at=AT, rng=random.Random(10))

    assert first.created == INTAKE_BATCH_SIZE
    assert second.created == 0
    assert Rider.objects.filter(development_squad__team=team).count() == INTAKE_BATCH_SIZE


def test_run_intake_writes_baseline_snapshots(team):
    squad = DevelopmentSquad.objects.create(team=team, level=1, opened_at=AT)

    run_intake(at=AT, rng=random.Random(11))

    riders = Rider.objects.filter(development_squad=squad)
    assert riders.count() == INTAKE_BATCH_SIZE
    for rider in riders:
        assert RiderAttributeSnapshot.objects.filter(rider=rider, week=None).exists()


def test_run_intake_into_a_full_squad_turns_the_whole_batch_away(team):
    """A squad with no free places gets nothing, and the loss is reported:
    the squad screen warns with the same number before the week arrives."""
    squad = DevelopmentSquad.objects.create(team=team, level=1, opened_at=AT)
    for index in range(LEVELS[squad.level].places):
        Rider.objects.create(
            name=f"Incumbent {index}", development_squad=squad,
            climb=20, sprint=20, flat=20, resistance=20, positioning=20,
        )

    result = run_intake(at=AT, rng=random.Random(20))

    assert result.created == 0
    assert result.turned_away == INTAKE_BATCH_SIZE
    assert in_squad(squad).count() == LEVELS[squad.level].places


def test_run_intake_into_a_squad_with_one_place_fills_only_that_place(team):
    """A partial batch: one rider arrives and one is lost, rather than the
    first being bumped for the second."""
    squad = DevelopmentSquad.objects.create(team=team, level=1, opened_at=AT)
    for index in range(LEVELS[squad.level].places - 1):
        Rider.objects.create(
            name=f"Incumbent {index}", development_squad=squad,
            climb=20, sprint=20, flat=20, resistance=20, positioning=20,
        )

    result = run_intake(at=AT, rng=random.Random(21))

    assert result.created == 1
    assert result.turned_away == 1
    assert in_squad(squad).count() == LEVELS[squad.level].places


def test_run_intake_does_not_count_graduates_against_the_places(team):
    """A graduate has left the squad and freed their place, so a batch lands
    in full even when the squad is full of graduates."""
    squad = DevelopmentSquad.objects.create(team=team, level=1, opened_at=AT)
    earlier = AT - timedelta(weeks=4)
    for index in range(LEVELS[squad.level].places):
        Rider.objects.create(
            name=f"Graduate {index}", development_squad=squad,
            intake_at=earlier, graduated_at=earlier,
            climb=20, sprint=20, flat=20, resistance=20, positioning=20,
        )

    result = run_intake(at=AT, rng=random.Random(22))

    assert result.created == INTAKE_BATCH_SIZE
    assert result.turned_away == 0
    assert in_squad(squad).count() == INTAKE_BATCH_SIZE
    assert graduates(squad).count() == LEVELS[squad.level].places
