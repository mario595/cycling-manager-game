"""Growth, decline and ageing: the age curve made live.

Pure functions over the Rider table. This module knows nothing about
seasons, weeks or the clock — `riders/` may not import `schedule/` or
`world/` (AGENTS.md). The caller (world.services.tick) decides when these
run and how many weeks to apply.
"""

from __future__ import annotations

from .generation import SPECIALITY_PROFILES
from .models import ENGINE_ATTRIBUTES, Rider

#: Fraction of the remaining gap to its ceiling an attribute closes each
#: week, at maximum growth. Tuned so a young rider well below potential
#: gains 10-20 stored points across a twelve-week season — one to two
#: points on the floored 0-10 display scale (riders/display.py).
WEEKLY_GROWTH_FRACTION = 0.035

#: Stored points a rider at decline_rate 100 loses per week, per year past
#: peak_age. Tuned so a rider two years past peak with an average decline
#: rate loses roughly a display point across a season.
WEEKLY_DECLINE_UNIT = 0.010

MIN_ATTRIBUTE = 1
MAX_ATTRIBUTE = 100


def attribute_ceilings(rider: Rider) -> dict[str, float]:
    """Per-attribute ceilings preserving the rider's speciality shape.

    `potential` is one number but a rider has five attributes. Growing
    them all toward `potential` would flatten every rider into the same
    profile by their peak age and destroy speciality. Scaling by the same
    SPECIALITY_PROFILES weights that generated the rider keeps the shape
    the player already sees. See the plan's Design decision 3.
    """
    profile = SPECIALITY_PROFILES[rider.speciality]
    mean_weight = sum(profile.values()) / len(profile)
    return {
        name: rider.potential * (profile[name] / mean_weight)
        for name in ENGINE_ATTRIBUTES
    }


def weekly_deltas(rider: Rider, weeks: int = 1) -> dict[str, float]:
    """Fractional attribute movement over `weeks` weeks.

    Two halves joined at peak_age, not one polynomial — growth speed and
    decline speed are governed by different traits (potential vs
    decline_rate) and must be tunable apart. See Design decision 4.

    `weeks > 1` is exact, not iterated: closing fraction `f` of the gap
    `w` times closes `1 - (1-f)**w` of it. A four-week catch-up is one
    calculation, not four passes over the table (Design decision 7).
    """
    ceilings = attribute_ceilings(rider)
    deltas: dict[str, float] = {}

    if rider.age < rider.peak_age:
        # Geometric approach: fast while the gap is wide, tapering to
        # nothing as the rider nears both their ceiling and their peak.
        # This *is* the rising half of the parabola.
        closed = 1 - (1 - WEEKLY_GROWTH_FRACTION) ** weeks
        for name in ENGINE_ATTRIBUTES:
            gap = ceilings[name] - getattr(rider, name)
            # Clamped at zero: a young rider already at their ceiling
            # holds, never falls. Only the decline half lowers an
            # attribute (Design decision 10).
            deltas[name] = max(0.0, gap) * closed
    else:
        years_past = rider.age - rider.peak_age
        per_week = WEEKLY_DECLINE_UNIT * rider.decline_rate * years_past
        for name in ENGINE_ATTRIBUTES:
            deltas[name] = -per_week * weeks

    return deltas
