from __future__ import annotations

from datetime import timedelta

import pytest

from riders.models import Rider
from schedule.models import SEASON_WEEKS, Season, Week
from world.clocks import MockClock
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


def test_tick_expires_low_value_long_unattached_riders(db):
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