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


class SameLevel(DevelopmentSquadError):
    """The team is already at that level — there is nothing to change to."""


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
