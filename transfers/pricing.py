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
VALUE_AT_MIN_STRENGTH = 800
VALUE_AT_MAX_STRENGTH = 157_000

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
_MIN_AGE = 17
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


def market_value_for(rider, field_factor: float = 1.0) -> int:
    """This rider's market value in whole credits. Pure: no database
    access, safe on an unsaved Rider. No floor above zero — a rider far
    past their best with little season left is worth very little, and the
    number says so plainly rather than being propped up (spec's *Rules and
    edge cases*).

    `field_factor` values the rider against the field, the same factor
    salaries use (#166, riders.models.FieldLevel). Live callers pass
    riders.field_level.current_field_factor(); 1.0 is a fresh world."""
    scaled = max(0.0, min(1.0, strength(rider) * field_factor / 100)) ** _STRENGTH_EXPONENT
    base = VALUE_AT_MIN_STRENGTH + (VALUE_AT_MAX_STRENGTH - VALUE_AT_MIN_STRENGTH) * scaled
    base *= career_horizon(rider.age)
    return max(0, _round_to_nearest_1000(base))


#: Fee percentages as fractions of market_value_for (Design decision 3). Signing at 60% lands roughly seven weeks of an
#: average rider's own wages (value ≈ one season ≈ twelve weeks, so 60% ≈
#: seven) — a real but survivable hit against STARTING_BALANCE. Severance
#: at half the signing rate: real cost, but releasing gives up an asset
#: rather than buying one.
SIGNING_FEE_RATE = 0.60
SEVERANCE_FEE_RATE = 0.30


def signing_fee_for(rider, field_factor: float = 1.0) -> int:
    """SIGNING_FEE_RATE of this rider's market value, rounded the same way
    market_value_for rounds (nearest 1,000)."""
    return _round_to_nearest_1000(SIGNING_FEE_RATE * market_value_for(rider, field_factor))


def severance_fee_for(rider, field_factor: float = 1.0) -> int:
    """SEVERANCE_FEE_RATE of this rider's market value, rounded the same
    way."""
    return _round_to_nearest_1000(SEVERANCE_FEE_RATE * market_value_for(rider, field_factor))


#: Reserve price as a fraction of market_value_for — the auction's
#: starting bid. Below SIGNING_FEE_RATE (0.60): a seller choosing to
#: auction accepts a lower guaranteed floor than a buyer would pay to sign
#: the same rider as a free agent outright, in exchange for the chance of
#: a higher price through competition (Design decision 5).
RESERVE_RATE = 0.50

#: Minimum bid increment as a fraction of the FROZEN reserve price, not
#: the live current price — an increment that tracked the rising current
#: price would punish exactly the contested, late-bidding auctions the
#: deadline extension is meant to protect (Design decision 6).
MIN_INCREMENT_RATE = 0.05


def reserve_price_for(rider, field_factor: float = 1.0) -> int:
    """RESERVE_RATE of this rider's market value, rounded the same way
    market_value_for rounds (nearest 1,000)."""
    return _round_to_nearest_1000(RESERVE_RATE * market_value_for(rider, field_factor))


def min_increment_for(reserve_price: int) -> int:
    """MIN_INCREMENT_RATE of a frozen reserve_price, rounded to the
    nearest 1,000. Takes the already-computed reserve, not a rider, so it
    stays correct even though reserve_price is frozen on the Auction row
    and never re-derived (Design decision 5)."""
    return max(1000, _round_to_nearest_1000(MIN_INCREMENT_RATE * reserve_price))
