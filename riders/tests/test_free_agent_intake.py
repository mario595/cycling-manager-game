from __future__ import annotations

import random
from datetime import datetime, timezone as dt_timezone

from riders.free_agent_intake import (
    FREE_AGENT_AGE_RANGE,
    FREE_AGENT_INTAKE_SIZE,
    is_free_agent_intake_week,
    run_free_agent_intake,
)
from riders.models import Rider, RiderAttributeSnapshot

AT = datetime(2027, 3, 1, tzinfo=dt_timezone.utc)


def test_intake_weeks_are_every_other_week():
    assert [n for n in range(1, 13) if is_free_agent_intake_week(n)] == [2, 4, 6, 8, 10, 12]


def test_an_intake_adds_a_batch_of_teamless_riders_dated_to_the_week(db):
    created = run_free_agent_intake(at=AT, rng=random.Random(1))

    assert len(created) == FREE_AGENT_INTAKE_SIZE
    riders = Rider.objects.filter(pk__in=[rider.pk for rider in created])
    assert riders.count() == FREE_AGENT_INTAKE_SIZE
    low, high = FREE_AGENT_AGE_RANGE
    for rider in riders:
        assert rider.team_id is None
        assert rider.development_squad_id is None
        assert rider.retired_at is None
        assert rider.unattached_since == AT
        assert low <= rider.age <= high
        assert rider.weekly_salary > 0


def test_intake_riders_are_in_the_free_agent_pool(db):
    from transfers.services import free_agents

    created = run_free_agent_intake(at=AT, rng=random.Random(2))

    assert set(free_agents().values_list("pk", flat=True)) == {rider.pk for rider in created}


def test_every_intake_rider_gets_a_baseline_snapshot(db):
    created = run_free_agent_intake(at=AT, rng=random.Random(3))

    assert RiderAttributeSnapshot.objects.filter(
        rider__in=created, week=None,
    ).count() == FREE_AGENT_INTAKE_SIZE


def test_intake_riders_are_priced_at_the_last_measured_field_level(db):
    # #166: a price set mid-season uses the level from the last close.
    from riders.models import FieldLevel
    from riders.pricing import weekly_salary_for

    FieldLevel.objects.create(factor=0.9)

    created = run_free_agent_intake(at=AT, rng=random.Random(3))

    for rider in created:
        assert rider.weekly_salary == weekly_salary_for(rider, 0.9)
