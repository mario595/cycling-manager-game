from __future__ import annotations

from datetime import datetime, timezone as dt_timezone

from economy.models import STARTING_BALANCE, LedgerEntry
from economy.services import (
    balance_for,
    ensure_opening_balance,
    entries_for,
    pay_race_prizes,
    reset_to_starting_balance,
)


def test_balance_is_zero_with_no_entries(db, team):
    assert balance_for(team) == 0


def test_balance_sums_signed_amounts(db, team):
    at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    LedgerEntry.objects.create(
        team=team, kind=LedgerEntry.Kind.STARTING_BALANCE, amount=500_000,
        occurred_at=at, description="Starting balance",
    )
    LedgerEntry.objects.create(
        team=team, kind=LedgerEntry.Kind.WAGES, amount=-14_400,
        occurred_at=at, description="Weekly wages",
    )

    assert balance_for(team) == 485_600


def test_ensure_opening_balance_is_idempotent(db, team):
    at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    first = ensure_opening_balance(team, at=at)
    second = ensure_opening_balance(team, at=at)

    assert first.pk == second.pk
    assert balance_for(team) == STARTING_BALANCE
    assert LedgerEntry.objects.filter(team=team).count() == 1


def test_ensure_opening_balance_stamps_game_time(db, team):
    at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)

    entry = ensure_opening_balance(team, at=at)

    assert entry.occurred_at == at


def test_reset_writes_the_difference(db, team):
    at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    LedgerEntry.objects.create(
        team=team, kind=LedgerEntry.Kind.STARTING_BALANCE, amount=STARTING_BALANCE,
        occurred_at=at, description="Starting balance",
    )
    LedgerEntry.objects.create(
        team=team, kind=LedgerEntry.Kind.WAGES, amount=-14_400,
        occurred_at=at, description="Weekly wages",
    )

    reset_to_starting_balance(team, at=at)

    # The prior entries must still exist — this is the append-only guarantee.
    assert entries_for(team).count() == 3
    assert balance_for(team) == STARTING_BALANCE


def test_reset_at_starting_balance_writes_nothing(db, team):
    at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    LedgerEntry.objects.create(
        team=team, kind=LedgerEntry.Kind.STARTING_BALANCE, amount=STARTING_BALANCE,
        occurred_at=at, description="Starting balance",
    )

    assert reset_to_starting_balance(team, at=at) is None
    assert LedgerEntry.objects.filter(team=team).count() == 1


def test_pay_race_prizes_writes_one_entry_per_placement(db, team, race):
    at = datetime(2027, 3, 2, 0, 0, tzinfo=dt_timezone.utc)
    prizes_by_team = {team.pk: [(2, 15_000), (5, 8_000)]}

    written = pay_race_prizes(
        race.pk, race_name=race.name, at=at, prizes_by_team=prizes_by_team
    )

    assert written == 2
    rows = list(LedgerEntry.objects.filter(team=team).order_by("position"))
    assert [row.position for row in rows] == [2, 5]
    assert [row.amount for row in rows] == [15_000, 8_000]
    assert all(row.kind == LedgerEntry.Kind.PRIZE_MONEY for row in rows)
    assert all(row.race_id == race.pk for row in rows)
    assert all(row.occurred_at == at for row in rows)
    assert all(row.description == f"Prize money — {race.name}" for row in rows)


def test_pay_race_prizes_is_idempotent(db, team, race):
    at = datetime(2027, 3, 2, 0, 0, tzinfo=dt_timezone.utc)
    prizes_by_team = {team.pk: [(2, 15_000), (5, 8_000)]}

    pay_race_prizes(race.pk, race_name=race.name, at=at, prizes_by_team=prizes_by_team)

    assert pay_race_prizes(
        race.pk, race_name=race.name, at=at, prizes_by_team=prizes_by_team
    ) == 0
    assert LedgerEntry.objects.filter(team=team).count() == 2


def test_pay_race_prizes_completes_a_partial_payout(db, team, race):
    at = datetime(2027, 3, 2, 0, 0, tzinfo=dt_timezone.utc)
    LedgerEntry.objects.create(
        team=team,
        kind=LedgerEntry.Kind.PRIZE_MONEY,
        amount=15_000,
        occurred_at=at,
        race=race,
        position=2,
        description=f"Prize money — {race.name}",
    )
    prizes_by_team = {team.pk: [(2, 15_000), (5, 8_000)]}

    written = pay_race_prizes(
        race.pk, race_name=race.name, at=at, prizes_by_team=prizes_by_team
    )

    assert written == 1
    rows = list(LedgerEntry.objects.filter(team=team).order_by("position"))
    assert [row.position for row in rows] == [2, 5]
    assert rows[0].amount == 15_000
    assert rows[1].amount == 8_000