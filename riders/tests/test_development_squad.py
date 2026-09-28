from __future__ import annotations

from datetime import datetime, timezone as dt_timezone

import pytest
from django.db import IntegrityError, transaction

from riders.development_squad import (
    LEVELS,
    DevelopmentSquadError,
    SameLevel,
    change_fee,
    weekly_cost,
)
from riders.models import DevelopmentSquad


def _open(team, level):
    return DevelopmentSquad.objects.create(
        team=team,
        level=level,
        opened_at=datetime(2027, 3, 1, tzinfo=dt_timezone.utc),
    )


def test_levels_rise_strictly_in_both_columns():
    """Load-bearing, not a balance note: change_fee's upgrade rule is a
    difference of opening fees, so a level that costs more to open but less
    to run would make upgrading cheaper than opening at the target directly
    (spec, *Rules and edge cases*)."""
    levels = [LEVELS[level] for level in sorted(LEVELS)]

    assert [terms.level for terms in levels] == [1, 2, 3]
    for cheaper, dearer in zip(levels, levels[1:]):
        assert dearer.opening_fee > cheaper.opening_fee
        assert dearer.weekly_cost > cheaper.weekly_cost


def test_weekly_cost_reads_the_table():
    assert weekly_cost(1) == LEVELS[1].weekly_cost == 1_500
    assert weekly_cost(3) == LEVELS[3].weekly_cost == 6_000


def test_change_fee_from_closed_is_opening_fee():
    for level, terms in LEVELS.items():
        assert change_fee(None, level) == terms.opening_fee


def test_change_fee_upgrade_is_difference():
    assert change_fee(1, 2) == LEVELS[2].opening_fee - LEVELS[1].opening_fee
    assert change_fee(1, 3) == LEVELS[3].opening_fee - LEVELS[1].opening_fee
    assert change_fee(2, 3) == LEVELS[3].opening_fee - LEVELS[2].opening_fee


def test_change_fee_downgrade_is_zero():
    assert change_fee(3, 1) == 0
    assert change_fee(2, 1) == 0


def test_change_fee_same_level_raises():
    with pytest.raises(SameLevel):
        change_fee(2, 2)
    assert issubclass(SameLevel, DevelopmentSquadError)


def test_one_squad_per_team(team):
    _open(team, 1)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _open(team, 2)


def test_level_out_of_range_rejected_by_db(team):
    squad = _open(team, 2)

    squad.level = 4
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            squad.save(update_fields=["level"])

    squad.level = 0
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            squad.save(update_fields=["level"])


def test_closed_squad_is_no_row_at_all(team):
    """Closing deletes the row rather than flagging it, so a team that has
    never opened one has no row to find — and a level is only ever meaningful
    while the squad is open."""
    assert not DevelopmentSquad.objects.filter(team=team).exists()
