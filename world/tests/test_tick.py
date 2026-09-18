from __future__ import annotations

from datetime import timedelta

import pytest

from economy.models import (
    MERCHANDISE_FANBASE_PER_CREDIT,
    STARTING_FANBASE,
    WEEKLY_FANBASE_DECAY,
    WEEKLY_WAGE_PER_RIDER,
    FanbaseEntry,
    LedgerEntry,
)
from racing.models import Race
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


def give_starting_fanbase(team, at):
    FanbaseEntry.objects.create(
        team=team, kind=FanbaseEntry.Kind.STARTING, delta=STARTING_FANBASE,
        occurred_at=at, description="Starting fanbase",
    )


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


def test_week_one_has_no_preceding_week_and_only_decays(db, team, riders):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    give_starting_fanbase(team, at=now())
    clock.set(week_one.starts_at + timedelta(hours=1))

    run = tick()

    assert run.fanbase_entries == 1
    row = FanbaseEntry.objects.get(team=team, kind=FanbaseEntry.Kind.WEEKLY)
    assert row.week == week_one
    assert row.points == 0
    assert row.delta == -WEEKLY_FANBASE_DECAY
    assert sum(FanbaseEntry.objects.filter(team=team).values_list("delta", flat=True)) == (
        STARTING_FANBASE - WEEKLY_FANBASE_DECAY
    )


def test_fanbase_reads_the_completed_week_not_the_opening_one(db, team, riders):
    # The load-bearing test for D2: entering week 2 must adjust fanbase off
    # week 1's points, because week 2's own races have not run yet when its
    # week transition is processed. An implementation that reads the opening
    # week gets points == 0 and a pure-decay delta.
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    week_two = season.weeks.get(number=2)
    give_starting_fanbase(team, at=now())
    Race.objects.create(
        name="Week One Race",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=week_one.starts_at + timedelta(hours=1),
        status=Race.Status.SCHEDULED,
        week=week_one,
    )

    clock.set(week_one.starts_at + timedelta(hours=1))
    tick()  # week 1 opens: pure decay, then the race is run and scored

    clock.set(week_two.starts_at + timedelta(hours=1))
    tick()  # week 2 opens: now week 1's points land

    week_two_row = FanbaseEntry.objects.get(
        team=team, kind=FanbaseEntry.Kind.WEEKLY, week=week_two
    )
    assert week_two_row.points > 0
    assert week_two_row.delta > -WEEKLY_FANBASE_DECAY

    week_one_row = FanbaseEntry.objects.get(
        team=team, kind=FanbaseEntry.Kind.WEEKLY, week=week_one
    )
    assert week_one_row.points == 0  # the week's own races come later
    assert week_one_row.delta == -WEEKLY_FANBASE_DECAY


def test_tick_pays_merchandise_after_updating_fanbase(db, team, riders):
    # The load-bearing test for D7: merchandise must be paid off the
    # post-adjustment fanbase, not whatever it was before this week's change.
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    week_two = season.weeks.get(number=2)
    give_starting_fanbase(team, at=now())
    Race.objects.create(
        name="Week One Race",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=week_one.starts_at + timedelta(hours=1),
        status=Race.Status.SCHEDULED,
        week=week_one,
    )

    clock.set(week_one.starts_at + timedelta(hours=1))
    tick()

    before = sum(FanbaseEntry.objects.filter(team=team).values_list("delta", flat=True))

    clock.set(week_two.starts_at + timedelta(hours=1))
    tick()

    week_two_row = FanbaseEntry.objects.get(
        team=team, kind=FanbaseEntry.Kind.WEEKLY, week=week_two
    )
    after = before + week_two_row.delta
    assert after > before  # the fanbase actually moved this week

    entry = LedgerEntry.objects.get(
        team=team, kind=LedgerEntry.Kind.MERCHANDISE, week=week_two
    )
    assert entry.amount == after // MERCHANDISE_FANBASE_PER_CREDIT


def test_catch_up_across_three_weeks_writes_three_fanbase_and_three_merchandise_entries(
    db, team, riders
):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_three = season.weeks.get(number=3)
    give_starting_fanbase(team, at=now())
    clock.set(week_three.starts_at + timedelta(hours=1))

    run = tick()

    assert run.weeks_processed == 3
    assert run.fanbase_entries == 3
    assert run.merchandise_entries == 3
    fanbase_rows = FanbaseEntry.objects.filter(
        team=team, kind=FanbaseEntry.Kind.WEEKLY
    ).order_by("week__number")
    assert fanbase_rows.count() == 3
    assert set(fanbase_rows.values_list("week_id", flat=True)) == {
        season.weeks.get(number=n).pk for n in (1, 2, 3)
    }
    assert set(fanbase_rows.values_list("occurred_at", flat=True)) == {
        season.weeks.get(number=n).starts_at for n in (1, 2, 3)
    }
    merch_rows = LedgerEntry.objects.filter(
        team=team, kind=LedgerEntry.Kind.MERCHANDISE
    ).order_by("week__number")
    assert merch_rows.count() == 3
    assert set(merch_rows.values_list("occurred_at", flat=True)) == {
        season.weeks.get(number=n).starts_at for n in (1, 2, 3)
    }


def test_tick_run_counts_fanbase_and_merchandise_entries(db, team, riders):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    give_starting_fanbase(team, at=now())
    clock.set(week_one.starts_at + timedelta(hours=1))

    run = tick()

    assert run.fanbase_entries == 1
    assert run.merchandise_entries == 1
    assert FanbaseEntry.objects.filter(team=team, kind=FanbaseEntry.Kind.WEEKLY).count() == 1
    assert LedgerEntry.objects.filter(
        team=team, kind=LedgerEntry.Kind.MERCHANDISE
    ).count() == 1
