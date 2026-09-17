from __future__ import annotations

from datetime import datetime, timezone as dt_timezone

from economy.models import STARTING_BALANCE, LedgerEntry
from economy.services import balance_for, ensure_opening_balance, entries_for, reset_to_starting_balance


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
    first = ensure_opening_balance(team)
    second = ensure_opening_balance(team)

    assert first.pk == second.pk
    assert balance_for(team) == STARTING_BALANCE
    assert LedgerEntry.objects.filter(team=team).count() == 1


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

    reset_to_starting_balance(team)

    # The prior entries must still exist — this is the append-only guarantee.
    assert entries_for(team).count() == 3
    assert balance_for(team) == STARTING_BALANCE


def test_reset_at_starting_balance_writes_nothing(db, team):
    at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    LedgerEntry.objects.create(
        team=team, kind=LedgerEntry.Kind.STARTING_BALANCE, amount=STARTING_BALANCE,
        occurred_at=at, description="Starting balance",
    )

    assert reset_to_starting_balance(team) is None
    assert LedgerEntry.objects.filter(team=team).count() == 1