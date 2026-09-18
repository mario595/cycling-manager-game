from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone

import pytest

from economy.models import (
    FANBASE_PER_POINT,
    MINIMUM_FANBASE,
    STARTING_FANBASE,
    WEEKLY_FANBASE_DECAY,
    FanbaseEntry,
)
from economy.services import (
    apply_weekly_fanbase,
    ensure_starting_fanbase,
    fanbase_entries_for,
    fanbase_for,
    reset_fanbase,
)
from schedule.models import Season, Week


@pytest.fixture
def week(db) -> Week:
    monday = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    season = Season.objects.create(number=1, starts_at=monday)
    return Week.objects.create(
        season=season,
        number=1,
        starts_at=monday,
        ends_at=monday + timedelta(weeks=1),
    )


def test_fanbase_is_sum_of_deltas(db, team):
    at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    FanbaseEntry.objects.create(
        team=team, kind=FanbaseEntry.Kind.STARTING, delta=STARTING_FANBASE,
        occurred_at=at, description="Starting fanbase",
    )
    FanbaseEntry.objects.create(
        team=team, kind=FanbaseEntry.Kind.WEEKLY, delta=250,
        occurred_at=at, description="Weekly fanbase change",
    )
    FanbaseEntry.objects.create(
        team=team, kind=FanbaseEntry.Kind.WEEKLY, delta=-150,
        occurred_at=at, description="Weekly fanbase change",
    )

    assert fanbase_for(team) == STARTING_FANBASE + 100


def test_ensure_starting_fanbase_is_idempotent(db, team):
    at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    first = ensure_starting_fanbase(team, at=at)
    second = ensure_starting_fanbase(team, at=at)

    assert first.pk == second.pk
    assert fanbase_for(team) == STARTING_FANBASE
    assert fanbase_entries_for(team).count() == 1


def test_reset_fanbase_returns_none_when_already_at_start(db, team):
    at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    ensure_starting_fanbase(team, at=at)

    assert reset_fanbase(team, at=at) is None
    assert fanbase_entries_for(team).count() == 1


def test_reset_fanbase_writes_takeover_delta_without_deleting_history(db, team):
    at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    FanbaseEntry.objects.create(
        team=team, kind=FanbaseEntry.Kind.STARTING, delta=STARTING_FANBASE,
        occurred_at=at, description="Starting fanbase",
    )
    FanbaseEntry.objects.create(
        team=team, kind=FanbaseEntry.Kind.WEEKLY, delta=20_000,
        occurred_at=at, description="Weekly fanbase change",
    )

    assert fanbase_for(team) == 30_000
    reset_fanbase(team, at=at)

    # The prior entries must still exist — this is the append-only guarantee.
    assert fanbase_entries_for(team).count() == 3
    assert fanbase_for(team) == STARTING_FANBASE


def test_points_raise_fanbase_net_of_decay(db, team, week):
    FanbaseEntry.objects.create(
        team=team, kind=FanbaseEntry.Kind.STARTING, delta=STARTING_FANBASE,
        occurred_at=week.starts_at, description="Starting fanbase",
    )

    written = apply_weekly_fanbase(week, points_by_team={team.pk: 10})

    assert written == 1
    row = FanbaseEntry.objects.get(team=team, kind=FanbaseEntry.Kind.WEEKLY)
    assert row.points == 10
    assert row.delta == 10 * FANBASE_PER_POINT - WEEKLY_FANBASE_DECAY == 250
    assert fanbase_for(team) == STARTING_FANBASE + 250


def test_scoreless_team_only_decays(db, team, week):
    FanbaseEntry.objects.create(
        team=team, kind=FanbaseEntry.Kind.STARTING, delta=STARTING_FANBASE,
        occurred_at=week.starts_at, description="Starting fanbase",
    )

    apply_weekly_fanbase(week, points_by_team={})  # absent key, treated as 0

    row = FanbaseEntry.objects.get(team=team, kind=FanbaseEntry.Kind.WEEKLY)
    assert row.points == 0
    assert row.delta == -WEEKLY_FANBASE_DECAY


def test_decay_applies_to_winners_too(db, team, week):
    FanbaseEntry.objects.create(
        team=team, kind=FanbaseEntry.Kind.STARTING, delta=STARTING_FANBASE,
        occurred_at=week.starts_at, description="Starting fanbase",
    )

    apply_weekly_fanbase(week, points_by_team={team.pk: 20})

    row = FanbaseEntry.objects.get(team=team, kind=FanbaseEntry.Kind.WEEKLY)
    assert row.delta < 20 * FANBASE_PER_POINT  # a winning week still pays decay


def test_fanbase_never_falls_below_floor(db, team, week):
    FanbaseEntry.objects.create(
        team=team, kind=FanbaseEntry.Kind.STARTING, delta=MINIMUM_FANBASE,
        occurred_at=week.starts_at, description="Starting fanbase",
    )

    apply_weekly_fanbase(week, points_by_team={})

    row = FanbaseEntry.objects.get(team=team, kind=FanbaseEntry.Kind.WEEKLY)
    # Assert on the stored delta AND the sum: clamping on read would make
    # fanbase_for look right while a raw −150 row sat in history.
    assert row.delta == 0
    assert fanbase_for(team) == MINIMUM_FANBASE


def test_second_call_for_same_week_writes_nothing(db, team, week):
    FanbaseEntry.objects.create(
        team=team, kind=FanbaseEntry.Kind.STARTING, delta=STARTING_FANBASE,
        occurred_at=week.starts_at, description="Starting fanbase",
    )

    first = apply_weekly_fanbase(week, points_by_team={team.pk: 10})
    second = apply_weekly_fanbase(week, points_by_team={team.pk: 10})

    assert first == 1
    assert second == 0
    assert fanbase_entries_for(team).filter(kind=FanbaseEntry.Kind.WEEKLY).count() == 1
    assert fanbase_for(team) == STARTING_FANBASE + 250