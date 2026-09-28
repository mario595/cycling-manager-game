from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone

import pytest

from economy.models import STARTING_BALANCE, LedgerEntry
from economy.services import (
    balance_for,
    charge_development_squad_costs,
    charge_development_squad_fee,
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


def test_weekly_cost_debits_each_team_in_map(db, team, other_team, week):
    written = charge_development_squad_costs(
        week, cost_by_team={team.pk: (3_500, "National"), other_team.pk: (1_500, "Regional")}
    )

    assert written == 2
    entries = LedgerEntry.objects.filter(kind=LedgerEntry.Kind.DEVELOPMENT_SQUAD, week=week)
    assert entries.count() == 2
    assert set(entries.values_list("team_id", flat=True)) == {team.pk, other_team.pk}
    assert entries.get(team=team).amount == -3_500
    assert entries.get(team=other_team).amount == -1_500


def test_weekly_row_is_dated_at_week_start_and_names_the_level(db, team, week):
    charge_development_squad_costs(week, cost_by_team={team.pk: (6_000, "Elite")})

    entry = LedgerEntry.objects.get(team=team, kind=LedgerEntry.Kind.DEVELOPMENT_SQUAD)
    assert entry.occurred_at == week.starts_at
    assert entry.description == "Development squad — Elite"
    assert entry.week_id == week.pk


def test_weekly_cost_is_idempotent_per_week(db, team, week):
    charge_development_squad_costs(week, cost_by_team={team.pk: (3_500, "National")})
    total_after_first = LedgerEntry.objects.filter(team=team).count()

    assert charge_development_squad_costs(week, cost_by_team={team.pk: (3_500, "National")}) == 0

    assert LedgerEntry.objects.filter(team=team).count() == total_after_first
    assert LedgerEntry.objects.get(team=team, kind=LedgerEntry.Kind.DEVELOPMENT_SQUAD).amount == -3_500


def test_a_fee_is_not_blocked_by_the_weekly_constraint(db, team, week):
    """The one-off fee deliberately sits outside the (team, week) unique
    constraint: an upgrade and a reopen in the same week are two distinct
    things the player paid for, and both belong in the ledger."""
    charge_development_squad_costs(week, cost_by_team={team.pk: (3_500, "National")})
    at = week.starts_at + timedelta(days=2)

    for description in ("Upgraded development squad to Elite", "Opened development squad — Regional"):
        charge_development_squad_fee(team, amount=-45_000, at=at, description=description)

    assert LedgerEntry.objects.filter(team=team, kind=LedgerEntry.Kind.DEVELOPMENT_SQUAD_FEE).count() == 2


def test_team_absent_from_map_gets_no_row(db, team, week):
    assert charge_development_squad_costs(week, cost_by_team={}) == 0
    assert not LedgerEntry.objects.filter(kind=LedgerEntry.Kind.DEVELOPMENT_SQUAD).exists()


def test_fee_writes_negative_row_with_description(db, team, week):
    at = week.starts_at + timedelta(days=2)

    charge_development_squad_fee(
        team, amount=-75_000, at=at, description="Opened development squad — National"
    )

    entry = LedgerEntry.objects.get(team=team, kind=LedgerEntry.Kind.DEVELOPMENT_SQUAD_FEE)
    assert entry.amount == -75_000
    assert entry.occurred_at == at
    assert entry.description == "Opened development squad — National"
    assert entry.week_id is None, "a one-off fee belongs to no week"


def test_kind_accepts_21_char_value(db, team):
    """Guards the widened `kind`. Postgres enforces varchar(32) rather than
    Django enforcing max_length, so without the AlterField the very first fee
    would fail at the database with a value-too-long error instead of here.
    `development_squad_fee` is the longest name in use at 21 characters, one
    more than the old limit of 20."""
    entry = LedgerEntry(
        team=team,
        kind=LedgerEntry.Kind.DEVELOPMENT_SQUAD_FEE,
        amount=-1,
        occurred_at=datetime(2027, 3, 1, tzinfo=dt_timezone.utc),
        description="Widest kind in use",
    )

    entry.full_clean(exclude=["week", "race"])
    entry.save()

    assert len(LedgerEntry.Kind.DEVELOPMENT_SQUAD_FEE) == 21
    assert entry.kind == "development_squad_fee"


def test_costs_and_fees_reduce_the_balance(db, team, week):
    ensure_opening_balance(team, at=week.starts_at)

    charge_development_squad_costs(week, cost_by_team={team.pk: (3_500, "National")})
    charge_development_squad_fee(
        team,
        amount=-75_000,
        at=week.starts_at,
        description="Opened development squad — National",
    )

    assert balance_for(team) == STARTING_BALANCE - 3_500 - 75_000
