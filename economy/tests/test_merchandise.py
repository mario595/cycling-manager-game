from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone

import pytest

from economy.models import (
    MERCHANDISE_FANBASE_PER_CREDIT,
    STARTING_FANBASE,
    FanbaseEntry,
    LedgerEntry,
)
from economy.services import balance_for, pay_merchandise
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


def _give_fanbase(team, delta, at):
    FanbaseEntry.objects.create(
        team=team, kind=FanbaseEntry.Kind.STARTING, delta=delta,
        occurred_at=at, description="Starting fanbase",
    )


def test_merchandise_is_fanbase_over_divisor(db, team, week):
    _give_fanbase(team, STARTING_FANBASE, week.starts_at)

    written = pay_merchandise(week)

    assert written == 1
    entry = LedgerEntry.objects.get(team=team, kind=LedgerEntry.Kind.MERCHANDISE)
    assert entry.amount == STARTING_FANBASE // MERCHANDISE_FANBASE_PER_CREDIT == 400
    assert entry.week_id == week.pk
    assert entry.occurred_at == week.starts_at


def test_merchandise_is_a_positive_ledger_entry(db, team, week):
    _give_fanbase(team, STARTING_FANBASE, week.starts_at)

    pay_merchandise(week)

    entry = LedgerEntry.objects.get(team=team, kind=LedgerEntry.Kind.MERCHANDISE)
    assert entry.amount > 0
    assert balance_for(team) == entry.amount  # income landed in the balance


def test_zero_fanbase_team_gets_a_zero_entry_not_a_skip(db, team, week):
    written = pay_merchandise(week)

    assert written == 1
    entry = LedgerEntry.objects.get(team=team, kind=LedgerEntry.Kind.MERCHANDISE)
    assert entry.amount == 0


def test_second_call_for_same_week_writes_nothing(db, team, week):
    _give_fanbase(team, STARTING_FANBASE, week.starts_at)

    first = pay_merchandise(week)
    second = pay_merchandise(week)

    assert first == 1
    assert second == 0
    assert LedgerEntry.objects.filter(
        team=team, kind=LedgerEntry.Kind.MERCHANDISE
    ).count() == 1