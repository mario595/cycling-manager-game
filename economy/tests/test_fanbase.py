from __future__ import annotations

from datetime import datetime, timezone as dt_timezone

from economy.models import STARTING_FANBASE, FanbaseEntry
from economy.services import (
    ensure_starting_fanbase,
    fanbase_entries_for,
    fanbase_for,
    reset_fanbase,
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