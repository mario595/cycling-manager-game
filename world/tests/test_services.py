from __future__ import annotations

from datetime import timedelta

import pytest

import world.services as world_services
from competitions.models import RacePoints
from racing.models import Race, RaceResult
from riders.models import Rider
from schedule.models import Season, SeasonTransition
from teams.models import Team
from world.clocks import MockClock
from world.models import GameClock
from world.services import get_clock, now, tick


@pytest.fixture
def team(db) -> Team:
    return Team.objects.create(name="Team Alpha", code="ALP", primary_colour="#FF0000")


@pytest.fixture
def four_riders(db, team) -> list[Rider]:
    return [
        Rider.objects.create(
            name=f"Rider {i}",
            team=team,
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


def test_tick_with_nothing_scheduled_does_nothing(db, four_riders):
    run = tick()

    assert run.races_started == 0
    assert run.races_finished == 0
    assert run.capped is False


def test_tick_runs_a_due_race_once(db, four_riders):
    clock: MockClock = get_clock()
    race = make_scheduled_race("Due Race", now() + timedelta(hours=1))
    clock.advance_to_next_due()

    run = tick()

    race.refresh_from_db()
    assert race.status == Race.Status.FINISHED
    assert race.finished_at == now()
    assert run.races_started == 1
    assert run.races_finished == 1
    assert RaceResult.objects.filter(race=race).count() == len(four_riders)


def test_tick_is_capped_at_catch_up_max_races(db, four_riders):
    clock: MockClock = get_clock()
    GameClock.load()
    GameClock.objects.filter(pk=1).update(catch_up_max_races=2)
    due_at = now() + timedelta(hours=1)
    for i in range(4):
        make_scheduled_race(f"Race {i}", due_at)
    clock.set(due_at)

    run = tick()

    assert run.races_started == 2
    assert run.capped is True
    assert Race.objects.filter(status=Race.Status.SCHEDULED).count() == 2


def test_tick_clamps_the_claim_limit_when_reclaimed_alone_exceeds_the_cap(db, four_riders):
    # Reclaimed races count against the same cap as newly-claimed ones. If
    # reclaimed races alone already exceed the cap, the claim limit must
    # clamp to zero rather than going negative (a negative slice stop would
    # silently return an empty queryset either way, but the cap must still
    # report correctly and nothing must error).
    GameClock.load()
    GameClock.objects.filter(pk=1).update(catch_up_max_races=1)
    for i in range(2):
        Race.objects.create(
            name=f"Stranded {i}", course=[{"length": 500.0, "gradient": 0.0}],
            starts_at=now() - timedelta(hours=1), status=Race.Status.RUNNING,
        )

    run = tick()

    assert run.capped is True
    assert Race.objects.filter(status=Race.Status.RUNNING).count() == 0


def test_second_tick_does_not_rerun_a_finished_race(db, four_riders):
    clock: MockClock = get_clock()
    race = make_scheduled_race("Once Only", now() + timedelta(hours=1))
    clock.advance_to_next_due()

    tick()
    race.refresh_from_db()
    assert race.status == Race.Status.FINISHED
    first_count = RaceResult.objects.filter(race=race).count()

    tick()
    race.refresh_from_db()
    assert race.status == Race.Status.FINISHED
    assert RaceResult.objects.filter(race=race).count() == first_count


def test_interrupted_race_is_reclaimed(db, four_riders):
    race = Race.objects.create(
        name="Stranded",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=now() - timedelta(hours=1),
        status=Race.Status.RUNNING,
    )

    run = tick()

    race.refresh_from_db()
    assert race.status == Race.Status.FINISHED
    assert RaceResult.objects.filter(race=race).count() == len(four_riders)
    assert run.races_finished >= 1


def test_race_failure_marks_failed_and_continues(db, four_riders):
    clock: MockClock = get_clock()
    due_at = now() + timedelta(hours=1)
    bad = make_scheduled_race("Broken Course", due_at, course=[{"length": "oops"}])
    good = make_scheduled_race("Good Race", due_at)
    clock.set(due_at)

    tick()

    bad.refresh_from_db()
    good.refresh_from_db()
    assert bad.status == Race.Status.FAILED
    assert good.status == Race.Status.FINISHED
    assert RaceResult.objects.filter(race=good).count() == len(four_riders)


def test_tick_scores_finished_races(db, four_riders, team):
    clock: MockClock = get_clock()
    race = make_scheduled_race("Due Race", now() + timedelta(hours=1))
    clock.advance_to_next_due()

    tick()

    assert RacePoints.objects.filter(race=race, team=team).exists()


def test_a_race_that_fails_to_score_is_marked_failed(db, four_riders, monkeypatch):
    clock: MockClock = get_clock()
    due_at = now() + timedelta(hours=1)
    bad = make_scheduled_race("Bad At Scoring", due_at)
    good = make_scheduled_race("Good Race", due_at)
    clock.set(due_at)

    original_score_race = world_services.score_race

    def _raise_for_bad(race):
        if race.pk == bad.pk:
            raise RuntimeError("scoring exploded")
        return original_score_race(race)

    monkeypatch.setattr("world.services.score_race", _raise_for_bad)

    tick()

    bad.refresh_from_db()
    good.refresh_from_db()
    assert bad.status == Race.Status.FAILED
    assert good.status == Race.Status.FINISHED
    assert RacePoints.objects.filter(race=good).exists()


def test_tick_records_a_season_opening(db):
    clock: MockClock = get_clock()
    season = Season.objects.create(number=1, starts_at=now())
    clock.set(season.starts_at + timedelta(hours=1))

    run = tick()

    assert run.seasons_opened == 1
    assert run.seasons_closed == 0
    assert SeasonTransition.objects.filter(
        season=season, kind=SeasonTransition.Kind.OPENED,
    ).exists()


def test_tick_does_not_record_a_transition_twice(db):
    clock: MockClock = get_clock()
    season = Season.objects.create(number=1, starts_at=now())
    clock.set(season.starts_at + timedelta(hours=1))

    first = tick()
    second = tick()

    assert first.seasons_opened == 1
    assert second.seasons_opened == 0
    assert SeasonTransition.objects.filter(
        season=season, kind=SeasonTransition.Kind.OPENED,
    ).count() == 1
