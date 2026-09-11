from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from racing.models import Race, RaceResult
from riders.models import Rider
from teams.models import Team
from world.models import GameClock, TickRun
from world.services import advance


@pytest.fixture
def team(db) -> Team:
    return Team.objects.create(name="Team Alpha", code="ALP", primary_colour="#FF0000")


@pytest.fixture
def four_riders(db, team) -> list[Rider]:
    return [
        Rider.objects.create(
            name=f"Rider {i}",
            team=team,
            role=Rider.Role.LEADER if i == 0 else Rider.Role.SUPPORT,
            climb=60,
            sprint=60,
            flat=60,
            resistance=60,
            positioning=60,
        )
        for i in range(4)
    ]


def make_scheduled_race(name: str, starts_at, course=None) -> Race:
    return Race.objects.create(
        name=name,
        course=course if course is not None else [{"length": 500.0, "gradient": 0.0}],
        starts_at=starts_at,
        status=Race.Status.SCHEDULED,
    )


def test_advance_with_nothing_scheduled_moves_time_only(db, four_riders):
    clock = GameClock.load()
    before = clock.current

    tick = advance()

    clock.refresh_from_db()
    assert clock.current > before
    assert tick.races_started == 0
    assert tick.races_finished == 0


def test_advance_runs_a_due_race_once(db, four_riders):
    clock = GameClock.load()
    race = make_scheduled_race("Due Race", clock.current + timedelta(hours=1))

    tick = advance(to_next=True)

    race.refresh_from_db()
    assert race.status == Race.Status.FINISHED
    assert tick.races_started == 1
    assert tick.races_finished == 1
    assert RaceResult.objects.filter(race=race).count() == len(four_riders)


def test_advance_is_capped_at_catch_up_hours(db, four_riders):
    clock = GameClock.load()
    clock.last_advanced_at = timezone.now() - timedelta(hours=200)
    clock.save(update_fields=["last_advanced_at"])
    before = clock.current

    tick = advance()

    clock.refresh_from_db()
    assert clock.current == before + timedelta(hours=72)
    assert tick.capped is True


def test_second_advance_does_not_rerun_a_finished_race(db, four_riders):
    clock = GameClock.load()
    race = make_scheduled_race("Once Only", clock.current + timedelta(hours=1))

    advance(to_next=True)
    race.refresh_from_db()
    assert race.status == Race.Status.FINISHED
    first_count = RaceResult.objects.filter(race=race).count()

    advance(to_next=True)
    race.refresh_from_db()
    assert race.status == Race.Status.FINISHED
    assert RaceResult.objects.filter(race=race).count() == first_count


def test_interrupted_race_is_reclaimed(db, four_riders):
    clock = GameClock.load()
    race = Race.objects.create(
        name="Stranded",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=clock.current - timedelta(hours=1),
        status=Race.Status.RUNNING,
    )

    tick = advance()

    race.refresh_from_db()
    assert race.status == Race.Status.FINISHED
    assert RaceResult.objects.filter(race=race).count() == len(four_riders)
    assert tick.races_finished >= 1


def test_race_failure_marks_failed_and_continues(db, four_riders):
    clock = GameClock.load()
    bad = make_scheduled_race(
        "Broken Course", clock.current + timedelta(hours=1), course=[{"length": "oops"}],
    )
    good = make_scheduled_race("Good Race", clock.current + timedelta(hours=1))

    advance(to_next=True)

    bad.refresh_from_db()
    good.refresh_from_db()
    assert bad.status == Race.Status.FAILED
    assert good.status == Race.Status.FINISHED
    assert RaceResult.objects.filter(race=good).count() == len(four_riders)
