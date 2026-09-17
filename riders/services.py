"""Growth, decline and ageing: the age curve made live.

Pure functions over the Rider table. This module knows nothing about
seasons, weeks or the clock — `riders/` may not import `schedule/` or
`world/` (AGENTS.md). The caller (world.services.tick) decides when these
run and how many weeks to apply.
"""

from __future__ import annotations

from django.db.models import F

from .generation import SPECIALITY_PROFILES
from .models import ENGINE_ATTRIBUTES, Rider

#: Fraction of the remaining gap to its ceiling an attribute closes each
#: week, at maximum growth. Tuned so a young rider well below potential
#: gains 10-20 stored points across a twelve-week season — one to two
#: points on the floored 0-10 display scale (riders/display.py).
WEEKLY_GROWTH_FRACTION = 0.035

#: Stored points a rider at decline_rate 100 loses per week, per year past
#: peak_age (capped at DECLINE_YEARS_CAP). Tuned so a rider several years
#: past peak with an *average* decline rate (50) loses roughly one to two
#: display points across a season — the spec's promised band
#: (specs/rider-growth-and-decline.md, In scope #7) for the representative
#: case, not just the ceiling — rather than compounding without bound the
#: longer a rider has been retired-in-all-but-name.
WEEKLY_DECLINE_UNIT = 0.006

#: Years past peak_age after which decline stops accelerating and holds
#: steady. Decline still "accelerates rather than being linear" for a
#: rider newly past their peak — the part of the curve where it matters
#: for a manager's decision — without an 18-years-past-peak veteran (the
#: model's age cap of 40 against the youngest possible peak_age of 22)
#: losing an implausible amount in one season.
DECLINE_YEARS_CAP = 3

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
        years_past = min(rider.age - rider.peak_age, DECLINE_YEARS_CAP)
        per_week = WEEKLY_DECLINE_UNIT * rider.decline_rate * years_past
        for name in ENGINE_ATTRIBUTES:
            deltas[name] = -per_week * weeks

    return deltas


def _settle(current: int, debt: float, delta: float) -> tuple[int, float]:
    """Fold `delta` into the accumulated `debt` and move out whole points.

    int() truncates toward zero, which is what both directions need: a
    debt of 2.7 yields +2 with 0.7 carried, and a debt of -2.7 yields -2
    with -0.7 carried. Using round() or floor() here would leak a point
    in one direction and is the likeliest bug in this file.
    """
    total = debt + delta
    whole = int(total)
    remainder = total - whole
    new_value = max(MIN_ATTRIBUTE, min(MAX_ATTRIBUTE, current + whole))
    # Clamped at the boundary: drop the carried remainder so it cannot
    # accumulate into a debt that never applies.
    if new_value != current + whole:
        remainder = 0.0
    return new_value, remainder


def apply_weekly_growth(weeks: int = 1) -> int:
    """Move every rider along their age curve by `weeks` weeks.

    Fractional movement accumulates in each rider's growth_debt rather
    than being rounded away each call — see Design decision 5. Returns
    how many riders had a stored attribute actually change.
    """
    changed = 0
    riders_to_update: list[Rider] = []
    for rider in Rider.objects.all():
        deltas = weekly_deltas(rider, weeks=weeks)
        debt = dict(rider.growth_debt)
        rider_changed = False
        for name in ENGINE_ATTRIBUTES:
            current = getattr(rider, name)
            new_value, remainder = _settle(current, debt.get(name, 0.0), deltas[name])
            debt[name] = remainder
            if new_value != current:
                setattr(rider, name, new_value)
                rider_changed = True
        rider.growth_debt = debt
        riders_to_update.append(rider)
        if rider_changed:
            changed += 1

    Rider.objects.bulk_update(riders_to_update, [*ENGINE_ATTRIBUTES, "growth_debt"])
    return changed


def advance_ages() -> int:
    """Advance every rider's age by one, capped at the model's maximum.

    A rider at the cap holds there until retirement (#42) exists. One
    UPDATE statement via F(), not a per-row loop.
    """
    return Rider.objects.filter(age__lt=40).update(age=F("age") + 1)
