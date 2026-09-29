"""What a development squad costs, and the ladder a team has to climb to reach
each level (#32).

The ladder is one step at a time and there is no way back down it. A squad
opens at the lowest level and is upgraded one level at a time from there; the
level above is *locked* until the one below is open. There is no downgrade —
the only way to spend less is to close the squad entirely, which is the
drastic measure a team short of money takes, and which forgets the level it
was at so a recovery starts from scratch. The reasoning is the spec's
(*Decisions taken*, "One step up, or all the way down").

Prices are a fixed table in `LEVELS`, never stored on the row: a stored price
could only ever drift from the table, the same reasoning `staff/pricing.py`
gives for a trainer's fee and salary. The model (`riders.DevelopmentSquad`)
holds which level a team runs at and nothing else.

`riders/` may not import `economy/` (AGENTS.md), so the operations here take
an injected `charge` callback rather than writing the fee themselves — the
pattern `staff.services.hire_trainer` establishes.

Closing releases every rider then sitting in the squad as a free agent
(#33) — see `close_squad`'s own docstring for why the release must happen
before the row is deleted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from django.db import IntegrityError, transaction
from teams.models import Team

from .models import DevelopmentSquad, Rider
from .services import mark_team_change


@dataclass(frozen=True)
class LevelTerms:
    """What one level costs: the one-off fee to open at it, and what it costs
    every week while it runs."""

    level: int
    name: str
    opening_fee: int
    weekly_cost: int


#: The three levels, cheapest first, forming a ladder climbed one rung at a
#: time: `level_status` opens the lowest and unlocks the next only once the one
#: below is open. Both columns rise strictly with level so the ladder is a
#: ladder — the top is the most expensive thing to enter *and* to run, and no
#: level is ever worth less than the one below it. (The original reason for
#: that, that an upgrade could undercut opening directly, cannot arise: there
#: is no way to open above the lowest level.)
#:
#: The numbers are tunable; the ordering is not, and a test enforces it.
#:
#: Calibrated against `economy.models.STARTING_BALANCE` (500,000) and a
#: ~14,400/week wage bill. Because each level costs its own fee to enter, the
#: total to reach a level is the *sum* of every fee below it: Elite is
#: 30,000 + 75,000 + 150,000 = 255,000 to climb, plus 72,000 of weekly costs
#: over a season — 65% of a starting balance, so Elite is a decision a team
#: makes with prize money and sponsorship behind it, not a default.
LEVELS: dict[int, LevelTerms] = {
    1: LevelTerms(1, DevelopmentSquad.Level.REGIONAL.label, 30_000, 1_500),
    2: LevelTerms(2, DevelopmentSquad.Level.NATIONAL.label, 75_000, 3_500),
    3: LevelTerms(3, DevelopmentSquad.Level.ELITE.label, 150_000, 6_000),
}

#: The one level a squad can be *opened* at, and therefore the base of the
#: ladder. Derived rather than written down, so adding a level above the top
#: cannot leave this stale.
ENTRY_LEVEL: int = min(LEVELS)

#: What a move onto a level is, as the server sees it. The SPA renders these
#: and never derives them, so a padlock on a card and a refusal from the
#: service come from the same function.
SquadAction = Literal["open", "upgrade", "current", "locked"]


@dataclass(frozen=True)
class LevelStatus:
    """One level's standing with a team: what the action on it is, and what the
    manager has to do first when there is no action.

    `note` is the only reason a level is locked, and it is never null for a
    locked level — a padlock with nothing to say behind it is a worse screen
    than no padlock.
    """

    action: SquadAction
    note: str | None = None


class DevelopmentSquadError(Exception):
    """Base class for a development squad change that cannot proceed."""


class SquadAlreadyOpen(DevelopmentSquadError):
    """The team already has a development squad; change its level or close it."""


class SquadNotOpen(DevelopmentSquadError):
    """The team has no development squad to change or close."""


class SameLevel(DevelopmentSquadError):
    """The team is already at that level — there is nothing to change to."""


class LevelLocked(DevelopmentSquadError):
    """The level needs the one below it open first, and it is not. Raised for
    opening above the lowest level and for skipping a rung on the way up."""


class CannotDowngrade(DevelopmentSquadError):
    """The team asked for a lower level. The ladder has no rungs pointing
    down: a squad is upgraded one level at a time or closed outright, and
    closing is the only way to spend less."""


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


def level_fee(level: int) -> int:
    """What moving a squad *onto* `level` costs, in whole credits.

    One figure per level, not per move: the lowest level's fee is what opens
    the squad, and every level above it charges its own full fee to upgrade
    into it. So climbing the ladder costs the sum of the fees — Elite is
    30,000 + 75,000 + 150,000 — and the fee a team is quoted for a level is
    the fee it will be charged, whatever route it took to get there.
    """
    terms = LEVELS.get(level)
    if terms is None:
        raise UnknownLevel(f"No development squad level {level!r}.")
    return terms.opening_fee


def level_status(current_level: int | None, target_level: int) -> LevelStatus:
    """What moving from `current_level` to `target_level` would be, and — when
    the answer is `locked` — what the team would have to do first. `None` for
    `current_level` means the squad is closed.

    Closed: the lowest level is an `open`, anything above it `locked` because
    the ladder is climbed from the bottom, so there is no door into the upper
    floors however rich the team is. Open: the level held is `current`, the one
    directly above it is the only `upgrade`, and everything else is `locked` —
    either a rung further up, or a level already climbed past.

    There is no "downgrade" answer, and that is the whole point: the way to
    spend less is `close_squad`, not a cheaper rung to step down to.

    A locked level has two quite different reasons and the screen has to tell
    them apart, so both live here rather than in the view: *"Open Regional
    first"* and *"Climbed past"* are different advice, and only this function
    knows which applies.

    **The only place the ladder rule lives.** `open_squad`, `change_level` and
    the API's per-level `action` all go through here, so the padlock the screen
    draws and the refusal the service raises cannot disagree.
    """
    if target_level not in LEVELS:
        raise UnknownLevel(f"No development squad level {target_level!r}.")
    if current_level is None:
        if target_level == ENTRY_LEVEL:
            return LevelStatus("open")
        return LevelStatus("locked", f"Open {LEVELS[ENTRY_LEVEL].name} first.")
    if target_level == current_level:
        return LevelStatus("current")
    if target_level == current_level + 1:
        return LevelStatus("upgrade")
    if target_level < current_level:
        return LevelStatus(
            "locked", "Climbed past. Close the squad to start over."
        )
    return LevelStatus("locked", f"Upgrade to {LEVELS[target_level - 1].name} first.")


def squad_for(team) -> DevelopmentSquad | None:
    """`team`'s development squad, or None when it has none open."""
    return DevelopmentSquad.objects.filter(team=team).first()


def _lock_team(team):
    """Take the `Team` row lock every squad operation shares.

    When the squad is closed there is no squad row to lock, so the team row
    is the only thing that serialises two concurrent "open" requests — and
    locking it for upgrade and close too gives all three operations one lock
    order. WITHOUT skip_locked, for
    `staff.services.hire_trainer`'s reason: the caller asked for this
    specific team, so a contended row must make us wait rather than
    silently behave as though the squad were not there.
    """
    Team.objects.select_for_update().get(pk=team.pk)


def open_squad(team, level: int, *, at, charge=None) -> DevelopmentSquad:
    """Open `team`'s development squad at `level`, debiting that level's fee.

    Only the lowest level can be opened. Anything above it raises LevelLocked
    however much the team can afford, because the ladder is climbed by
    upgrading: opening straight into National would sell the upper floors at a
    discount and make the rung below pointless to buy. So the one way in is
    `level` = the entry level, and a squad that has been closed and reopened
    starts there again.

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
    if level_status(None, level).action == "locked":
        raise LevelLocked(
            f"A development squad opens at {LEVELS[ENTRY_LEVEL].name}. "
            f"Reach {terms.name} by upgrading from there."
        )
    with transaction.atomic():
        _lock_team(team)
        if squad_for(team) is not None:
            raise SquadAlreadyOpen("Your development squad is already open.")

        if charge is not None:
            charge(level_fee(level), f"Opened development squad — {terms.name}")
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
    """Upgrade `team`'s open development squad to the level above it and return
    it, debiting that level's full fee.

    One rung, and only upwards. `level` two or more above the current one
    raises LevelLocked — the ladder has to be climbed, not vaulted — and any
    level below raises CannotDowngrade, because the ladder has no way back
    down: a manager who needs the weekly cost to stop closes the squad
    instead, and pays the entry fee again to reopen. The fee charged is the
    target level's own, not a difference against the current one, so quoting a
    level and charging it cannot drift.

    Instant, with no notice period and no waiting for a week boundary — the
    weekly cost simply switches rate from the next boundary (world/README.md,
    *How a tick works*). `charge` works exactly as it does in `open_squad`.

    Note this makes a mid-week upgrade backdated in the player's favour for
    the week already under way: the new level is charged at the next boundary,
    not for the half-week just gone, and nothing is prorated. That is the
    spec's own trade (plan, Design decision 7), and it matches how a trainer
    hired mid-week is treated.
    """
    terms = LEVELS.get(level)
    if terms is None:
        raise UnknownLevel(f"No development squad level {level!r}.")
    with transaction.atomic():
        _lock_team(team)
        squad = squad_for(team)
        if squad is None:
            raise SquadNotOpen("Your team has no development squad.")

        action = level_status(squad.level, level).action
        if action == "current":
            raise SameLevel("Your development squad is already at that level.")
        if action == "locked":
            if level < squad.level:
                raise CannotDowngrade(
                    "A development squad cannot go down a level. Close it to "
                    "stop the weekly cost — reopening starts from scratch."
                )
            raise LevelLocked(
                f"Upgrade to {LEVELS[level - 1].name} first."
            )

        if charge is not None:
            charge(
                level_fee(level),
                f"Upgraded development squad to {terms.name}",
            )
        squad.level = level
        squad.save(update_fields=["level", "updated_at"])
    return squad


def close_squad(team, *, at) -> bool:
    """Close `team`'s development squad if it has one, releasing every
    rider then in it as a free agent. Returns whether there was one to
    close.

    The row is deleted rather than flagged, and nothing is refunded or
    written to the ledger. Closing is the only way to reduce the weekly cost,
    and it forgets everything: reopening pays the entry level's fee again and
    starts the climb from the bottom, which is what makes it a credible last
    resort for a team that cannot afford to run one rather than a cheaper
    rung to step down to.

    Riders are released **before** the row is deleted (#33's plan, Design
    decision 6) — every squad rider is stamped `unattached_since = at` via
    the existing `mark_team_change`, then has `development_squad` cleared,
    and only then is the squad row deleted. Deleting first would let
    `development_squad`'s SET_NULL unlink them silently with no stamp, and a
    rider with a null `unattached_since` is never treated as long-unattached
    by the free-agent pool's expiry rule — it would sit in the market
    forever. `at` is game time, required so this stamp is never skipped.

    `teams.services.claim_team` calls this and ignores the return; the API
    turns False into a 409.
    """
    with transaction.atomic():
        _lock_team(team)
        squad = squad_for(team)
        if squad is None:
            return False
        riders = list(Rider.objects.filter(development_squad=squad))
        mark_team_change(riders, team_now=None, at=at)
        Rider.objects.filter(pk__in=[r.pk for r in riders]).update(development_squad=None)
        squad.delete()
    return True
