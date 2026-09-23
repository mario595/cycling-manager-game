"""What a rider is worth on the market. A pure function of visible
attributes and age — never a hidden trait, never stored. Recomputed on
every read so a rider who improves is worth more immediately (#31).
"""

from __future__ import annotations

from riders.pricing import strength

#: Market value at the bottom and top of the strength range (see
#: `riders.pricing.strength`). Calibrated against generated rosters, not
#: the theoretical 1-100 range — see transfers/tests/test_pricing.py's
#: calibration tests, which pin the average generated rider's value to
#: roughly one season of their own wages.
VALUE_AT_MIN_STRENGTH = 1_200
VALUE_AT_MAX_STRENGTH = 240_000

#: Same convex shape as riders.pricing.weekly_salary_for, and the same
#: exponent deliberately — the star premium should feel the same way in
#: both prices.
_STRENGTH_EXPONENT = 2.0

#: Age from which a rider's value starts falling. Below this, age does not
#: discount value at all — value is about years of career remaining, and a
#: rider this young has the whole career ahead of them.
_PEAK_VALUE_AGE = 23

#: The floor the age multiplier falls to at the model's maximum age. Never
#: zero: an old rider is worth little, not literally nothing.
_HORIZON_AT_MAX_AGE = 0.15

#: The model's own age validators (riders/models.py) — duplicated here so
#: this module stays self-contained arithmetic, same reasoning as
#: riders/pricing.py's own _MIN_AGE/_MAX_AGE.
_MIN_AGE = 18
_MAX_AGE = 40


def _round_to_nearest_1000(value: float) -> int:
    """Integer nearest-1000 rounding — a capital sum in the hundreds of
    thousands rounded to the nearest 50 (riders.pricing's convention for a
    weekly wage) reads as false precision. Not shared with riders/pricing.py:
    that helper is private, and the two roundings are different decisions."""
    return 1000 * round(value / 1000)


def career_horizon(age: int) -> float:
    """1.0 at or below _PEAK_VALUE_AGE, falling linearly to
    _HORIZON_AT_MAX_AGE at _MAX_AGE. Monotonically decreasing past the
    peak, unlike riders.pricing.age_multiplier, which is a symmetric
    penalty around a prime band — a valuation prices in years of career
    remaining, not current fitness for the job."""
    if age <= _PEAK_VALUE_AGE:
        return 1.0
    fraction = (age - _PEAK_VALUE_AGE) / (_MAX_AGE - _PEAK_VALUE_AGE)
    fraction = max(0.0, min(1.0, fraction))
    return 1.0 - (1.0 - _HORIZON_AT_MAX_AGE) * fraction


def market_value_for(rider) -> int:
    """This rider's market value in whole credits. Pure: no database
    access, safe on an unsaved Rider. No floor above zero — a rider far
    past their best with little season left is worth very little, and the
    number says so plainly rather than being propped up (spec's *Rules and
    edge cases*)."""
    scaled = max(0.0, min(1.0, strength(rider) / 100)) ** _STRENGTH_EXPONENT
    base = VALUE_AT_MIN_STRENGTH + (VALUE_AT_MAX_STRENGTH - VALUE_AT_MIN_STRENGTH) * scaled
    base *= career_horizon(rider.age)
    return max(0, _round_to_nearest_1000(base))
