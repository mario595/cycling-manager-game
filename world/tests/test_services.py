from __future__ import annotations

from datetime import timedelta

import pytest

import world.services as world_services
from competitions.models import RacePoints
from racing.models import Race, RaceResult
from riders.models import Rider
from schedule.models import SEASON_WEEKS, Season, SeasonTransition, Week
from teams.models import Team
from world.clocks import MockClock
from world.models import GameClock
from world.services import get_clock, now, tick


def make_season_with_weeks(number: int, starts_at) -> Season:
    season = Season.objects.create(number=number, starts_at=starts_at)
    for week_number in range(1, SEASON_WEEKS + 1):
        week_start = season.starts_at + timedelta(weeks=week_number - 1)
        Week.objects.create(
            season=season,
            number=week_number,
            starts_at=week_start,
            ends_at=week_start + timedelta(weeks=1),
        )
    return season


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


@pytest.fixture
def young_rider(db, team) -> Rider:
    return Rider.objects.create(
        name="Young Rider",
        team=team,
        speciality=Rider.Speciality.CLIMBER,
        age=20,
        peak_age=27,
        potential=90,
        decline_rate=50,
        climb=40,
        sprint=40,
        flat=40,
        resistance=40,
        positioning=40,
    )


def test_a_tick_applies_one_week_of_growth(db, young_rider):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    clock.set(week_one.starts_at + timedelta(hours=1))

    run = tick()
    young_rider.refresh_from_db()

    assert run.weeks_processed == 1
    # A young rider well below potential moves every week, even if the
    # movement is too small to cross a whole stored point yet.
    assert young_rider.climb > 40 or young_rider.growth_debt.get("climb", 0) > 0


def test_a_tick_three_weeks_late_applies_three_weeks_of_growth(db, young_rider):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_four = season.weeks.get(number=4)
    clock.set(week_four.starts_at + timedelta(hours=1))

    run = tick()

    assert run.weeks_processed == 4


def test_two_ticks_in_the_same_week_apply_growth_once(db, young_rider):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    clock.set(week_one.starts_at + timedelta(hours=1))

    tick()
    young_rider.refresh_from_db()
    after_first = (young_rider.climb, dict(young_rider.growth_debt))

    tick()
    young_rider.refresh_from_db()
    after_second = (young_rider.climb, dict(young_rider.growth_debt))

    assert after_first == after_second


def test_riders_age_when_a_season_closes(db, young_rider):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    clock.set(season.ends_at + timedelta(hours=1))

    run = tick()
    young_rider.refresh_from_db()

    assert run.riders_aged == 1
    assert young_rider.age == 21


def test_riders_do_not_age_mid_season(db, young_rider):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    clock.set(week_one.starts_at + timedelta(hours=1))

    run = tick()
    young_rider.refresh_from_db()

    assert run.riders_aged == 0
    assert young_rider.age == 20


def test_growth_is_applied_before_races_are_simulated(db, young_rider, team, monkeypatch):
    # A rider racing in the same tick their week's growth lands should
    # race with that week's attributes already applied. weeks_processed
    # and races_finished both being non-zero proves nothing about *order*
    # (either call order would produce the same counts), so this records
    # the actual call order and asserts growth happened first.
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    for i in range(3):
        Rider.objects.create(
            name=f"Teammate {i}", team=team,
            climb=60, sprint=60, flat=60, resistance=60, positioning=60,
        )
    Race.objects.create(
        name="Week One Race",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=week_one.starts_at + timedelta(hours=1),
        status=Race.Status.SCHEDULED,
    )
    clock.set(week_one.starts_at + timedelta(hours=1))

    call_order: list[str] = []
    original_apply_weekly_growth = world_services.apply_weekly_growth
    original_simulate_race = world_services.simulate_race

    def _record_growth(*args, **kwargs):
        call_order.append("growth")
        return original_apply_weekly_growth(*args, **kwargs)

    def _record_race(*args, **kwargs):
        call_order.append("race")
        return original_simulate_race(*args, **kwargs)

    monkeypatch.setattr("world.services.apply_weekly_growth", _record_growth)
    monkeypatch.setattr("world.services.simulate_race", _record_race)

    run = tick()

    assert run.weeks_processed == 1
    assert run.races_finished == 1
    assert call_order == ["growth", "race"]
