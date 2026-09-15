"""The player's 0-10 attribute scale, mapped from the stored 1-100 value.

Only ever used when shipping a value to the player — auto_pick_squad and
generation both keep working on the raw 1-100 attribute. See
specs/rider-attributes.md, *Display scale*.
"""

from __future__ import annotations


def to_display_scale(value: int) -> int:
    """Map a stored 1-100 attribute onto the 0-10 scale the player sees.

    Deliberately lossy: two riders at 71 and 74 both show 7. That is the
    point — see specs/rider-attributes.md, *Display scale*.
    """
    return round(value / 10)
