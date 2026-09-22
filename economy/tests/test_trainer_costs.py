from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone

import pytest

from economy.models import STARTING_BALANCE, LedgerEntry
from economy.services import (
    balance_for,
    charge_trainer_fee,
    charge_trainer_salaries,
    ensure_opening_balance,
)
from schedule.models import Season, Week


@pytest.fixture
def season(db) -> Season:
    return Season.objects.create(
        number=1,
        starts_at=datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc),
    )


@pytest.fixture
def week(season) -> Week:
    return Week.objects.create(
        season=season,
        number=1,
        starts_at=season.starts_at,
        ends_at=season.starts_at + timedelta(weeks=1),
    )


def test_charges_each_team_once(db, team, other_team, week):
    written = charge_trainer_salaries(
        week, salary_by_team={team.pk: 3_900, other_team.pk: 2_600}
    )

    assert written == 2
    entries = LedgerEntry.objects.filter(kind=LedgerEntry.Kind.TRAINER_SALARY, week=week)
    assert entries.count() == 2
    assert set(entries.values_list("team_id", flat=True)) == {team.pk, other_team.pk}


def test_amount_is_negative_and_dated_at_week_start(db, team, week):
    charge_trainer_salaries(week, salary_by_team={team.pk: 3_900})

    entry = LedgerEntry.objects.get(team=team, week=week)
    assert entry.amount == -3_900
    assert entry.occurred_at == week.starts_at
    assert entry.description == "Trainer salary"
    assert entry.rider_count == 0


def test_second_call_for_same_week_writes_nothing(db, team, week):
    charge_trainer_salaries(week, salary_by_team={team.pk: 3_900})
    first = LedgerEntry.objects.get(team=team, week=week)
    total_after_first = LedgerEntry.objects.filter(team=team).count()

    assert charge_trainer_salaries(week, salary_by_team={team.pk: 3_900}) == 0

    first.refresh_from_db()
    assert first.amount == -3_900
    assert LedgerEntry.objects.filter(team=team).count() == total_after_first


def test_team_without_a_trainer_is_not_charged(db, team, week):
    assert charge_trainer_salaries(week, salary_by_team={}) == 0
    assert LedgerEntry.objects.filter(kind=LedgerEntry.Kind.TRAINER_SALARY).count() == 0


def test_charges_reduce_the_balance(db, team, week):
    at = week.starts_at
    ensure_opening_balance(team, at=at)

    charge_trainer_salaries(week, salary_by_team={team.pk: 3_900})

    assert balance_for(team) == STARTING_BALANCE - 3_900


def test_fee_is_a_negative_entry_at_the_given_time(db, team, week):
    at = week.starts_at + timedelta(days=2)

    charge_trainer_fee(team, amount=-46_800, at=at, description="Hired Coach One")

    entry = LedgerEntry.objects.get(team=team, kind=LedgerEntry.Kind.TRAINER_FEE)
    assert entry.amount == -46_800
    assert entry.occurred_at == at
    assert entry.description == "Hired Coach One"
    assert entry.week_id is None
    assert balance_for(team) == -46_800


def test_several_fees_over_a_season_is_fine(db, team):
    for n in range(2):
        charge_trainer_fee(
            team,
            amount=-46_800,
            at=datetime(2027, 3, 1 + n, 1, 0, tzinfo=dt_timezone.utc),
            description="Hired Coach One",
        )

    assert LedgerEntry.objects.filter(team=team, kind=LedgerEntry.Kind.TRAINER_FEE).count() == 2