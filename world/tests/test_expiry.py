from __future__ import annotations

from datetime import timedelta

import pytest

from riders.models import Rider
from riders.services import retire_riders
from racing.models import Race, RaceResult
from schedule.models import SEASON_WEEKS, Season, Week
import world.services as world_services
from world.clocks import MockClock
from world.services import get_clock, now, tick


@pytest.fixture(autouse=True)
def _no_free_agent_intake(monkeypatch):
    """These tests build an exact pool to put a known rider in its bottom
    quintile. Free-agent intake (#157) adds riders to the pool every other
    week, which would move that cutoff, so it is switched off here; its own
    tests are in test_free_agent_intake.py."""
    monkeypatch.setattr(world_services, "run_free_agent_intake", lambda **kwargs: [])


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


def _agent(name, *, unattached_since, **attrs) -> Rider:
    defaults = dict(
        name=name,
        team=None,
        flat=15, climb=30, sprint=30, resistance=30, positioning=30,
    )
    defaults.update(attrs)
    return Rider.objects.create(unattached_since=unattached_since, **defaults)


def _five_agent_pool() -> list[Rider]:
    """A strong free agent plus four weak ones — the smallest pool whose
    bottom EXPIRY_VALUE_PERCENTILE is a real, one-rider quintile."""
    strong = Rider.objects.create(
        name="Strong", team=None, flat=90, climb=90, sprint=90,
        resistance=90, positioning=90,
    )
    weak = [
        Rider.objects.create(
            name=f"Weak {i}", team=None, flat=15, climb=30, sprint=30,
            resistance=30, positioning=30,
        )
        for i in range(4)
    ]
    return [strong, *weak]


# -- _expire_free_agents / tick() ---------------------------------------


def test_expiry_deletes_a_never_raced_rider(db):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    agents = _five_agent_pool()
    joined_weeks_ago = season.weeks.get(number=1).starts_at
    for agent in agents:
        agent.unattached_since = joined_weeks_ago
        agent.save(update_fields=["unattached_since"])
    clock.set(season.weeks.get(number=11).starts_at + timedelta(hours=1))

    run = tick()

    assert run.agents_expired == 4
    assert run.agents_retired == 0
    names = set(Rider.objects.values_list("name", flat=True))
    assert "Strong" in names
    assert not {"Weak 0", "Weak 1", "Weak 2", "Weak 3"} & names


def test_tick_does_not_expire_a_high_value_unattached_rider(db):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    joined_weeks_ago = season.weeks.get(number=1).starts_at
    recently = season.weeks.get(number=10).starts_at
    # The strong rider has been unattached the whole time, but its value
    # sits above the bottom quintile — the value gate keeps it.
    _agent(
        "Strong", flat=90, climb=90, sprint=90, resistance=90, positioning=90,
        unattached_since=joined_weeks_ago,
    )
    for i in range(4):
        _agent(f"Weak {i}", flat=15, unattached_since=recently)
    clock.set(season.weeks.get(number=11).starts_at + timedelta(hours=1))

    run = tick()

    assert Rider.objects.filter(name="Strong").exists()
    assert run.agents_expired == 0


def test_tick_does_not_expire_a_recently_unattached_rider(db):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    joined_weeks_ago = season.weeks.get(number=1).starts_at
    recently = season.weeks.get(number=10).starts_at
    # Four long-unattached riders a notch above the recent weakling, so the
    # bottom-quintile cutoff lands exactly on the recent rider's value —
    # only its recency saves it.
    for i in range(4):
        _agent(f"Older {i}", flat=30, unattached_since=joined_weeks_ago)
    recent = _agent("Recent Weak", flat=15, unattached_since=recently)
    clock.set(season.weeks.get(number=11).starts_at + timedelta(hours=1))

    run = tick()

    assert Rider.objects.filter(pk=recent.pk).exists()
    assert run.agents_expired == 0


def test_tick_never_expires_a_rider_with_null_unattached_since(db):
    """Load-bearing: pre-migration free agents carry a null
    `unattached_since` and must never be treated as "unattached since the
    beginning of time" — one tick must not silently delete them. The null
    rider is deliberately as weak, long-eligible-as-it-would-be as the four
    tracked ones, so *only* the null exclusion can save it."""
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    joined_weeks_ago = season.weeks.get(number=1).starts_at
    for i in range(4):
        _agent(f"Tracked {i}", flat=15, unattached_since=joined_weeks_ago)
    untracked = _agent("Untracked", flat=15, unattached_since=None)
    clock.set(season.weeks.get(number=11).starts_at + timedelta(hours=1))

    run = tick()

    assert Rider.objects.filter(pk=untracked.pk).exists()
    assert run.agents_expired == 4


def test_expiry_retires_a_raced_rider_and_keeps_their_results(db):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    agents = _five_agent_pool()
    joined_weeks_ago = season.weeks.get(number=3).starts_at
    for agent in agents:
        agent.unattached_since = joined_weeks_ago
        agent.save(update_fields=["unattached_since"])

    raced = agents[1]
    race = Race.objects.create(
        name=f"Race for {raced.name}",
        course=[{"length": 500.0, "gradient": 0.0}],
    )
    result = RaceResult.objects.create(
        race=race, rider=raced, position=1, finish_time=100.0,
    )
    clock.set(season.weeks.get(number=11).starts_at + timedelta(hours=1))

    run = tick()

    assert run.agents_retired == 1
    assert run.agents_expired == 3
    raced.refresh_from_db()
    assert raced.team_id is None
    assert raced.retired_at == season.weeks.get(number=11).starts_at
    assert RaceResult.objects.filter(pk=result.pk).exists()


def test_a_dnf_counts_as_having_raced(db):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    agents = _five_agent_pool()
    joined_weeks_ago = season.weeks.get(number=3).starts_at
    for agent in agents:
        agent.unattached_since = joined_weeks_ago
        agent.save(update_fields=["unattached_since"])

    raced = agents[1]
    race = Race.objects.create(
        name=f"DNF for {raced.name}",
        course=[{"length": 500.0, "gradient": 0.0}],
    )
    result = RaceResult.objects.create(
        race=race, rider=raced, position=1, finish_time=None,
    )
    clock.set(season.weeks.get(number=11).starts_at + timedelta(hours=1))

    run = tick()

    assert run.agents_retired == 1
    assert run.agents_expired == 3
    raced.refresh_from_db()
    assert raced.team_id is None
    assert raced.retired_at == season.weeks.get(number=11).starts_at
    assert RaceResult.objects.filter(pk=result.pk).exists()


def test_retired_riders_do_not_count_toward_the_expiry_percentile(db):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    agents = _five_agent_pool()
    joined_weeks_ago = season.weeks.get(number=1).starts_at
    for agent in agents:
        agent.unattached_since = joined_weeks_ago
        agent.save(update_fields=["unattached_since"])
    retired = [
        Rider.objects.create(
            name=f"Retired {i}", team=None, flat=1, climb=1, sprint=1,
            resistance=1, positioning=1, unattached_since=joined_weeks_ago,
            retired_at=joined_weeks_ago,
        )
        for i in range(3)
    ]
    clock.set(season.weeks.get(number=11).starts_at + timedelta(hours=1))

    run = tick()

    assert run.agents_retired == 0
    assert run.agents_expired == 4
    assert Rider.objects.filter(pk__in=[rider.pk for rider in retired]).count() == 3
    assert Rider.objects.filter(name="Strong").exists()
    assert not Rider.objects.filter(name__startswith="Weak ").exists()


def test_a_retired_rider_is_untouched_by_later_ticks(db):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    rider = Rider.objects.create(
        name="Frozen Rider", team=None, flat=20, climb=20, sprint=20,
        resistance=20, positioning=20, age=25, potential=100, peak_age=27,
        freshness=40, weekly_salary=1,
        growth_debt={"climb": 0.5, "sprint": 0.5, "flat": 0.5,
                     "resistance": 0.5, "positioning": 0.5},
        unattached_since=week_one.starts_at,
    )
    retired_at = season.weeks.get(number=11).starts_at
    assert retire_riders([rider.pk], at=retired_at) == 1
    clock.set(retired_at + timedelta(hours=1))
    tick()

    rider.refresh_from_db()
    before = {
        "age": rider.age,
        "freshness": rider.freshness,
        "weekly_salary": rider.weekly_salary,
        "growth_debt": rider.growth_debt,
        "retired_at": rider.retired_at,
        "attributes": tuple(
            getattr(rider, attribute)
            for attribute in ("climb", "sprint", "flat", "resistance", "positioning")
        ),
    }

    clock.set(season.ends_at + timedelta(hours=1))
    tick()
    rider.refresh_from_db()

    after = {
        "age": rider.age,
        "freshness": rider.freshness,
        "weekly_salary": rider.weekly_salary,
        "growth_debt": rider.growth_debt,
        "retired_at": rider.retired_at,
        "attributes": tuple(
            getattr(rider, attribute)
            for attribute in ("climb", "sprint", "flat", "resistance", "positioning")
        ),
    }
    assert after == before
