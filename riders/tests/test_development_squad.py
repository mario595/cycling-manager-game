from __future__ import annotations

from datetime import datetime, timezone as dt_timezone

import pytest
from django.db import IntegrityError, transaction

from economy.models import LedgerEntry
from riders.development_squad import (
    LEVELS,
    DevelopmentSquadError,
    InsufficientFunds,
    SameLevel,
    SquadAlreadyOpen,
    SquadNotOpen,
    UnknownLevel,
    change_fee,
    change_level,
    close_squad,
    open_squad,
    squad_for,
    weekly_cost,
)
from riders.models import DevelopmentSquad

#: The game time every test opens a squad at. Game time, not wall clock.
OPENED_AT = datetime(2027, 3, 1, tzinfo=dt_timezone.utc)


class RecordingCharge:
    """A `charge` callback that records what it was asked to book and writes a
    real ledger row, the way api/'s callback does. It has to write one: the
    claim under test is that a raising charge takes its fee row down with it,
    which is a claim about the database, not about the arguments passed in.

    The `kind` is a stand-in — the development squad kinds arrive with W3 —
    because nothing here reads it back. `riders/` itself may not import
    `economy/` (AGENTS.md); a test may.
    """

    def __init__(self, team, raise_on_call: Exception | None = None):
        self.team = team
        self.calls: list[tuple[int, str]] = []
        self.raise_on_call = raise_on_call

    def __call__(self, amount: int, description: str) -> None:
        self.calls.append((amount, description))
        LedgerEntry.objects.create(
            team=self.team,
            kind=LedgerEntry.Kind.TRAINER_FEE,
            amount=-amount,
            occurred_at=OPENED_AT,
            description=description,
        )
        if self.raise_on_call is not None:
            raise self.raise_on_call


def _open(team, level):
    return DevelopmentSquad.objects.create(team=team, level=level, opened_at=OPENED_AT)


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


def test_open_creates_squad_and_charges_opening_fee(team):
    charge = RecordingCharge(team)

    squad = open_squad(team, 2, at=OPENED_AT, charge=charge)

    assert squad.level == 2
    assert squad.team_id == team.pk
    assert squad.opened_at == OPENED_AT
    assert charge.calls == [(LEVELS[2].opening_fee, "Opened development squad — National")]


def test_open_without_a_callback_is_free(team):
    squad = open_squad(team, 1, at=OPENED_AT)

    assert squad.level == 1


def test_open_at_an_unknown_level_raises(team):
    charge = RecordingCharge(team)

    with pytest.raises(UnknownLevel):
        open_squad(team, 4, at=OPENED_AT, charge=charge)

    assert charge.calls == []
    assert not DevelopmentSquad.objects.exists()


def test_open_when_open_raises_and_charges_nothing(team):
    _open(team, 1)
    charge = RecordingCharge(team)

    with pytest.raises(SquadAlreadyOpen):
        open_squad(team, 3, at=OPENED_AT, charge=charge)

    assert charge.calls == []
    assert squad_for(team).level == 1


def test_charge_raising_rolls_back_open(team):
    """The fee row is written by the callback before the squad row exists, so
    a refused opening has to take the fee with it — otherwise a player too
    poor to open a squad is charged for trying."""
    charge = RecordingCharge(team, raise_on_call=InsufficientFunds("You cannot afford this."))

    with pytest.raises(InsufficientFunds):
        open_squad(team, 1, at=OPENED_AT, charge=charge)

    assert charge.calls, "the callback should have run before the refusal"
    assert not DevelopmentSquad.objects.exists()
    assert not LedgerEntry.objects.filter(team=team).exists()


def test_upgrade_charges_difference(team):
    _open(team, 1)
    charge = RecordingCharge(team)

    squad = change_level(team, 3, charge=charge)

    assert squad.level == 3
    assert charge.calls == [
        (LEVELS[3].opening_fee - LEVELS[1].opening_fee, "Upgraded development squad to Elite"),
    ]


def test_downgrade_charges_nothing(team):
    _open(team, 3)
    charge = RecordingCharge(team)

    squad = change_level(team, 1, charge=charge)

    assert squad.level == 1
    assert charge.calls == []


def test_change_level_when_closed_raises(team):
    charge = RecordingCharge(team)

    with pytest.raises(SquadNotOpen):
        change_level(team, 2, charge=charge)

    assert charge.calls == []


def test_change_to_same_level_raises(team):
    _open(team, 2)
    charge = RecordingCharge(team)

    with pytest.raises(SameLevel):
        change_level(team, 2, charge=charge)

    assert charge.calls == []
    assert squad_for(team).level == 2


def test_change_to_an_unknown_level_raises(team):
    _open(team, 2)

    with pytest.raises(UnknownLevel):
        change_level(team, 9)

    assert squad_for(team).level == 2


def test_close_deletes_and_returns_true(team):
    _open(team, 2)

    assert close_squad(team) is True
    assert not DevelopmentSquad.objects.filter(team=team).exists()


def test_close_when_closed_returns_false(team):
    assert close_squad(team) is False


def test_reopen_after_close_charges_full_fee(team):
    _open(team, 3)
    close_squad(team)
    charge = RecordingCharge(team)

    squad = open_squad(team, 2, at=OPENED_AT, charge=charge)

    assert squad.level == 2
    # In full, not the difference: closing does not remember the old level.
    assert charge.calls == [(LEVELS[2].opening_fee, "Opened development squad — National")]


def test_every_refusal_is_one_exception_family(team):
    for refusal in (SquadAlreadyOpen, SquadNotOpen, SameLevel, UnknownLevel):
        assert issubclass(refusal, DevelopmentSquadError)
