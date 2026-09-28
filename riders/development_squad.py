"""What a development squad costs, and the rule for what moving between
levels costs (#32).

Prices are a fixed table in `LEVELS`, never stored on the row: a stored price
could only ever drift from the table, the same reasoning `staff/pricing.py`
gives for a trainer's fee and salary. The model (`riders.DevelopmentSquad`)
holds which level a team runs at and nothing else.

`riders/` may not import `economy/` (AGENTS.md), so the operations here take
an injected `charge` callback rather than writing the fee themselves — the
pattern `staff.services.hire_trainer` establishes.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.db import IntegrityError, transaction
from teams.models import Team

from .models import DevelopmentSquad


@dataclass(frozen=True)
class LevelTerms:
    """What one level costs: the one-off fee to open at it, and what it costs
    every week while it runs."""

    level: int
    name: str
    opening_fee: int
    weekly_cost: int


#: The three levels, cheapest first. Both columns rise strictly with level
#: (spec, *Rules and edge cases*): there is no level that costs more to open
#: but less to run. `change_fee` depends on it — an upgrade can only cost the
#: difference while fees ascend, which is what stops upgrading from being
#: cheaper than opening at the target level directly. The numbers are
#: tunable; the ordering is not, and a test enforces it.
#:
#: Calibrated against `economy.models.STARTING_BALANCE` (500,000) and a
#: ~14,400/week wage bill: Regional is roughly a mid-range trainer, and Elite's
#: first season (150,000 fee plus 72,000 of weekly costs) is ~44% of a
#: starting balance, so an Elite squad is a real bet.
LEVELS: dict[int, LevelTerms] = {
    1: LevelTerms(1, DevelopmentSquad.Level.REGIONAL.label, 30_000, 1_500),
    2: LevelTerms(2, DevelopmentSquad.Level.NATIONAL.label, 75_000, 3_500),
    3: LevelTerms(3, DevelopmentSquad.Level.ELITE.label, 150_000, 6_000),
}


class DevelopmentSquadError(Exception):
    """Base class for a development squad change that cannot proceed."""


class SquadAlreadyOpen(DevelopmentSquadError):
    """The team already has a development squad; change its level or close it."""


class SquadNotOpen(DevelopmentSquadError):
    """The team has no development squad to change or close."""


class SameLevel(DevelopmentSquadError):
    """The team is already at that level — there is nothing to change to."""


class UnknownLevel(DevelopmentSquadError):
    """No such development squad level. The API's ChoiceField catches this
    first, so this is the guard for any other caller."""


class InsufficientFunds(DevelopmentSquadError):
    """The team cannot afford the fee. Raised by the caller's `charge`
    callback, not here — declared in this family so a caller can catch one
    exception type for every way a squad change can be refused."""


def weekly_cost(level: int) -> int:
    """What running a squad at `level` costs every week."""
    return LEVELS[level].weekly_cost


def change_fee(current_level: int | None, target_level: int) -> int:
    """What moving from `current_level` to `target_level` costs, in whole
    credits.

    `current_level` of None means the squad is closed, so the target is an
    opening and costs its full opening fee. An upgrade costs the difference
    between the two levels' opening fees; a downgrade costs nothing, with no
    refund of what was already paid to reach the higher level — a downgrade
    is a decision to spend less from now on, not a chance to recover past
    spending. `target_level == current_level` raises SameLevel: there is no
    such thing as a free change that changes nothing.

    **The only place the upgrade rule lives.** Opening, changing level and the
    API's per-level `change_fee` all go through here, so the screen can never
    price a move the server would charge differently.
    """
    if current_level is not None and target_level == current_level:
        raise SameLevel("Your development squad is already at that level.")
    if current_level is None:
        return LEVELS[target_level].opening_fee
    if target_level < current_level:
        return 0
    return LEVELS[target_level].opening_fee - LEVELS[current_level].opening_fee


def squad_for(team) -> DevelopmentSquad | None:
    """`team`'s development squad, or None when it has none open."""
    return DevelopmentSquad.objects.filter(team=team).first()


def _lock_team(team):
    """Take the `Team` row lock every squad operation shares.

    When the squad is closed there is no squad row to lock, so the team row
    is the only thing that serialises two concurrent "open" requests — and
    locking it for upgrade, downgrade and close too gives all four
    operations one lock order. WITHOUT skip_locked, for
    `staff.services.hire_trainer`'s reason: the caller asked for this
    specific team, so a contended row must make us wait rather than
    silently behave as though the squad were not there.
    """
    Team.objects.select_for_update().get(pk=team.pk)


def open_squad(team, level: int, *, at, charge=None) -> DevelopmentSquad:
    """Open `team`'s development squad at `level`, debiting the opening fee.

    `charge` is an optional callable run immediately before the squad sticks
    — the caller (api/) passes it to book the fee and refuse the opening by
    raising InsufficientFunds, or anything else. It runs AFTER the state
    checks and BEFORE the row write, so a raise rolls the whole thing back
    and leaves no fee behind. `riders/` may not import `economy/` (AGENTS.md),
    so the debit is injected rather than imported — the pattern
    `staff.services.hire_trainer` establishes. Without charge, the opening
    is free, which is the path tests use.

    `at` is game time, the moment the squad opens, from the caller —
    `riders/` may not import `world/`.
    """
    terms = LEVELS.get(level)
    if terms is None:
        raise UnknownLevel(f"No development squad level {level!r}.")
    with transaction.atomic():
        _lock_team(team)
        if squad_for(team) is not None:
            raise SquadAlreadyOpen("Your development squad is already open.")

        if charge is not None:
            charge(change_fee(None, level), f"Opened development squad — {terms.name}")
        try:
            # A savepoint, so a failed insert leaves the enclosing
            # transaction usable: the fee row written above is rolled back by
            # the outer atomic() as the error propagates out of it, and the
            # caller sees SquadAlreadyOpen rather than a broken transaction.
            with transaction.atomic():
                return DevelopmentSquad.objects.create(
                    team=team, level=level, opened_at=at,
                )
        except IntegrityError:
            # The OneToOneField's unique index is the second line of defence,
            # behind the team lock above.
            raise SquadAlreadyOpen("Your development squad is already open.")


def change_level(team, level: int, *, charge=None) -> DevelopmentSquad:
    """Move `team`'s open development squad to `level` and return it.

    An upgrade debits the difference in opening fees; a downgrade charges
    nothing and refunds nothing. Instant, with no notice period and no
    waiting for a week boundary — the weekly cost simply switches rate from
    the next boundary (world/README.md, *How a tick works*). `charge` works
    exactly as it does in `open_squad`, and a downgrade never calls it.
    """
    terms = LEVELS.get(level)
    if terms is None:
        raise UnknownLevel(f"No development squad level {level!r}.")
    with transaction.atomic():
        _lock_team(team)
        squad = squad_for(team)
        if squad is None:
            raise SquadNotOpen("Your team has no development squad.")
        if level == squad.level:
            raise SameLevel("Your development squad is already at that level.")

        if level > squad.level and charge is not None:
            charge(
                change_fee(squad.level, level),
                f"Upgraded development squad to {terms.name}",
            )
        squad.level = level
        squad.save(update_fields=["level", "updated_at"])
    return squad


def close_squad(team) -> bool:
    """Close `team`'s development squad if it has one. Returns whether there
    was one to close.

    The row is deleted rather than flagged, and nothing is refunded or
    written to the ledger: a downgrade and a close are the same decision —
    spend less from now on, not a chance to recover past spending.
    `teams.services.claim_team` calls this and ignores the return; the API
    turns False into a 409.
    """
    with transaction.atomic():
        _lock_team(team)
        deleted, _ = DevelopmentSquad.objects.filter(team=team).delete()
    return deleted > 0
