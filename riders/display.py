"""The player's 0-10 attribute scale, mapped from the stored 1-100 value.

Only ever used when shipping a value to the player — auto_pick_squad and
generation both keep working on the raw 1-100 attribute. See
specs/rider-attributes.md, *Display scale*.
"""

from __future__ import annotations


def to_display_scale(value: int) -> int:
    """Map a stored 1-100 attribute onto the 0-10 scale the player sees.

    Floors, not rounds: a level is not reached until the stored value
    actually gets there. A rider at 58 shows 5, not 6 — the same reasoning
    that keeps a starting roster's ceiling well under 10 (see
    riders/generation.py, _MAX_STARTING_ATTRIBUTE) would be undercut by
    letting the display round a rider up to a level they have not reached.

    Deliberately lossy either way: two riders at 71 and 74 both show 7.
    That half of the point still holds — see specs/rider-attributes.md,
    *Display scale*.
    """
    return value // 10
