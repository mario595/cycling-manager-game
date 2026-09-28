from __future__ import annotations

from datetime import datetime, timezone as dt_timezone

import pytest
from django.db import IntegrityError, transaction

from economy.models import LedgerEntry
from riders.development_squad import (
    ENTRY_LEVEL,
    LEVELS,
    CannotDowngrade,
    DevelopmentSquadError,
    InsufficientFunds,
    LevelLocked,
    SameLevel,
    SquadAlreadyOpen,
    SquadNotOpen,
    UnknownLevel,
    change_level,
    close_squad,
    level_fee,
    level_status,
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
    """Load-bearing, not a balance note. The ladder is climbed for a fee at
    every rung, so the top has to be the most expensive thing to enter and to
    run — otherwise a player would rationally stop short of it, or climb to a
    level cheaper than the one they left (spec, *Rules and edge cases*).

    This is no longer about an upgrade undercutting a direct opening, which
    was the original reason: there is no way to open above the lowest level
    at all now, so that side door is shut structurally.
    """
    levels = [LEVELS[level] for level in sorted(LEVELS)]

    assert [terms.level for terms in levels] == [1, 2, 3]
    for cheaper, dearer in zip(levels, levels[1:]):
        assert dearer.opening_fee > cheaper.opening_fee
        assert dearer.weekly_cost > cheaper.weekly_cost


def test_weekly_cost_reads_the_table():
    assert weekly_cost(1) == LEVELS[1].weekly_cost == 1_500
    assert weekly_cost(3) == LEVELS[3].weekly_cost == 6_000


def test_level_fee_is_the_level_s_own_opening_fee():
    """One price per level, not per move: the entry level's fee is what opens
    the squad, and each level above charges its own in full to upgrade into
    it. So the figure quoted for a level is the figure charged, and climbing
    the ladder costs the sum of the fees."""
    for level, terms in LEVELS.items():
        assert level_fee(level) == terms.opening_fee


def test_climbing_to_the_top_costs_every_fee():
    """Elite is not reachable for its own fee: 30,000 to open at Regional,
    then 75,000 to reach National, then 150,000 to reach Elite. The spec's
    economy section quotes this total, so it is pinned here rather than left
    to drift when a number is retuned."""
    assert sum(level_fee(level) for level in sorted(LEVELS)) == 255_000


def test_level_fee_unknown_level_raises():
    with pytest.raises(UnknownLevel):
        level_fee(9)


def test_level_status_opens_only_the_entry_level_when_closed():
    assert level_status(None, ENTRY_LEVEL).action == "open"
    for level in sorted(LEVELS):
        if level == ENTRY_LEVEL:
            continue
        status = level_status(None, level)
        assert status.action == "locked"
        # Never null: a padlock with nothing behind it is a worse screen than
        # no padlock.
        assert status.note == f"Open {LEVELS[ENTRY_LEVEL].name} first."


def test_level_status_unlocks_only_the_next_level_up():
    for current in sorted(LEVELS):
        for target in sorted(LEVELS):
            status = level_status(current, target)
            if target == current:
                assert (status.action, status.note) == ("current", None)
            elif target == current + 1:
                assert (status.action, status.note) == ("upgrade", None)
            elif target < current:
                # Climbed past, not "needs a lower level" — the advice differs,
                # and only this function knows which applies.
                assert status.action == "locked"
                assert status.note == "Climbed past. Close the squad to start over."
            else:
                assert status.action == "locked"
                assert status.note == f"Upgrade to {LEVELS[target - 1].name} first."


def test_level_status_never_returns_a_downgrade():
    """The ladder has no rungs pointing down, so the word does not exist in
    the vocabulary the API hands the SPA — there is nothing for the screen to
    render as a cheaper move."""
    for current in list(LEVELS) + [None]:
        for target in LEVELS:
            assert level_status(current, target).action != "downgrade"


def test_every_locked_level_explains_itself():
    """A locked card is only useful if the manager can see what would unlock
    it, so no combination may produce a lock with no note."""
    for current in list(LEVELS) + [None]:
        for target in LEVELS:
            status = level_status(current, target)
            assert (status.note is not None) == (status.action == "locked")


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

    squad = open_squad(team, ENTRY_LEVEL, at=OPENED_AT, charge=charge)

    assert squad.level == ENTRY_LEVEL
    assert squad.team_id == team.pk
    assert squad.opened_at == OPENED_AT
    assert charge.calls == [(level_fee(1), "Opened development squad — Regional")]


def test_open_above_the_entry_level_raises(team):
    """The ladder is climbed, not entered at any height: however rich the team
    is, there is no door straight into National or Elite, because selling the
    top rung at its own price would make the rungs below pointless to buy."""
    for level in (2, 3):
        charge = RecordingCharge(team)

        with pytest.raises(LevelLocked):
            open_squad(team, level, at=OPENED_AT, charge=charge)

        assert charge.calls == []
        assert not DevelopmentSquad.objects.exists()


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
        open_squad(team, 1, at=OPENED_AT, charge=charge)

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


def test_upgrade_charges_the_target_level_s_own_fee(team):
    """The target level's full fee, not a difference against the one held, so
    the figure on the card and the figure in the ledger are the same number
    and the total cost of the climb is the sum of the fees."""
    _open(team, 1)
    charge = RecordingCharge(team)

    squad = change_level(team, 2, charge=charge)

    assert squad.level == 2
    assert charge.calls == [(level_fee(2), "Upgraded development squad to National")]

    charge = RecordingCharge(team)
    squad = change_level(team, 3, charge=charge)

    assert squad.level == 3
    assert charge.calls == [(level_fee(3), "Upgraded development squad to Elite")]


def test_upgrade_skipping_a_level_raises(team):
    """Elite is two rungs above Regional, and the ladder has to be walked: a
    jump would skip the fee for the middle rung entirely."""
    _open(team, 1)
    charge = RecordingCharge(team)

    with pytest.raises(LevelLocked):
        change_level(team, 3, charge=charge)

    assert charge.calls == []
    assert squad_for(team).level == 1


@pytest.mark.parametrize("current,target", [(3, 1), (3, 2), (2, 1)])
def test_downgrade_raises(team, current, target):
    """There is no way back down the ladder. A manager who needs the weekly
    cost to stop closes the squad and pays the entry fee again to reopen —
    which is the point: closing is a last resort, not a cheaper rung."""
    _open(team, current)
    charge = RecordingCharge(team)

    with pytest.raises(CannotDowngrade):
        change_level(team, target, charge=charge)

    assert charge.calls == []
    assert squad_for(team).level == current


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


def test_reopen_after_close_charges_full_fee_from_the_bottom(team):
    """Closing forgets the level, so a team that shuts down an Elite squad to
    stop the weekly cost and later recovers starts the climb again from
    Regional — the same position, and the same fee, as a team that never had
    one."""
    _open(team, 3)
    close_squad(team)
    charge = RecordingCharge(team)

    squad = open_squad(team, ENTRY_LEVEL, at=OPENED_AT, charge=charge)

    assert squad.level == ENTRY_LEVEL
    # In full, not a difference and not a discount for having been here before.
    assert charge.calls == [(level_fee(1), "Opened development squad — Regional")]


def test_reopen_above_the_entry_level_raises(team):
    """Even a team that had reached Elite cannot reopen at Elite, which is
    what makes a reopened squad start from scratch rather than resume."""
    _open(team, 3)
    close_squad(team)
    charge = RecordingCharge(team)

    with pytest.raises(LevelLocked):
        open_squad(team, 3, at=OPENED_AT, charge=charge)

    assert charge.calls == []


def test_every_refusal_is_one_exception_family(team):
    for refusal in (
        SquadAlreadyOpen,
        SquadNotOpen,
        SameLevel,
        LevelLocked,
        CannotDowngrade,
        UnknownLevel,
    ):
        assert issubclass(refusal, DevelopmentSquadError)
