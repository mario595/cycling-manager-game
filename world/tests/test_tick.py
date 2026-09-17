from __future__ import annotations

from datetime import timedelta

import pytest

from economy.models import WEEKLY_WAGE_PER_RIDER, LedgerEntry
from riders.models import Rider
from schedule.models import SEASON_WEEKS, Season, Week
from teams.models import Team
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


@pytest.fixture
def team(db) -> Team:
    return Team.objects.create(name="Team Alpha", code="ALP", primary_colour="#FF0000")


@pytest.fixture
def riders(db, team) -> list[Rider]:
    return [
        Rider.objects.create(
            name=f"Rider {i}",
            team=team,
            climb=60, sprint=60, flat=60, resistance=60, positioning=60,
        )
        for i in range(4)
    ]


def test_tick_charges_wages_for_the_week_it_crosses(db, team, riders):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    clock.set(week_one.starts_at + timedelta(hours=1))

    run = tick()

    assert run.wage_entries == 1
    entry = LedgerEntry.objects.get(team=team, kind=LedgerEntry.Kind.WAGES)
    assert entry.week == week_one
    assert entry.occurred_at == week_one.starts_at
    assert entry.amount == -(len(riders) * WEEKLY_WAGE_PER_RIDER)


def test_catch_up_charges_each_missed_week_separately(db, team, riders):
    # The load-bearing test for Design decision 3 (applied to wages): a
    # three-week jump must produce three separate wage entries dated to
    # three different weeks, never one lump sum and never skipped weeks.
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_three = season.weeks.get(number=3)
    clock.set(week_three.starts_at + timedelta(hours=1))

    run = tick()

    assert run.weeks_processed == 3
    assert run.wage_entries == 3
    entries = LedgerEntry.objects.filter(team=team, kind=LedgerEntry.Kind.WAGES).order_by("week__number")
    assert entries.count() == 3
    assert set(entries.values_list("week_id", flat=True)) == {
        season.weeks.get(number=n).pk for n in (1, 2, 3)
    }
    assert set(entries.values_list("week__starts_at", flat=True)) == {
        season.weeks.get(number=n).starts_at for n in (1, 2, 3)
    }


def test_running_tick_twice_does_not_double_charge(db, team, riders):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_two = season.weeks.get(number=2)
    clock.set(week_two.starts_at + timedelta(hours=1))

    first = tick()
    # Moving the clock on to a fresh week is the reason a second tick runs
    # at all; only the *new* week may be charged.
    clock.set(season.weeks.get(number=3).starts_at + timedelta(hours=1))
    second = tick()

    assert first.wage_entries == 2
    assert second.wage_entries == 1
    assert LedgerEntry.objects.filter(team=team, kind=LedgerEntry.Kind.WAGES).count() == 3


def test_tick_with_no_boundary_crossed_charges_nothing(db, team, riders):
    run = tick()

    assert run.wage_entries == 0
    assert not LedgerEntry.objects.filter(kind=LedgerEntry.Kind.WAGES).exists()