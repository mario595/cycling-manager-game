"""What a rider costs per week. Derived from visible attributes and age
only — never from a hidden trait. Stored on the rider at creation (see
specs/rider-salaries-plan.md, Design decision 1), not recomputed on read.
"""

from __future__ import annotations

from .generation import SPECIALITY_PROFILES
from .models import ENGINE_ATTRIBUTES

#: Weekly salary at the bottom and top of the strength range (see
#: `strength`, below). Calibrated against generated rosters, not the
#: theoretical 1-100 range: `riders.generation.QUALITY_SPREAD` and
#: `_MAX_STARTING_ATTRIBUTE` keep a generated rider's strength well under
#: 100 in practice, so these two constants and `_STRENGTH_EXPONENT` were
#: picked by sampling `generate_rider` — see the plan's Design decisions 5
#: and 6. Together they put roughly a 10x gap between a generated roster's
#: weakest and strongest rider, and an average roster within a few percent
#: of `economy.models.WEEKLY_WAGE_PER_RIDER`.
SALARY_AT_MIN_STRENGTH = 100
SALARY_AT_MAX_STRENGTH = 10_000

#: Convex interpolation between the two constants above: strength scaled
#: to 0-1 and raised to this power before scaling into the salary range.
#: >1 means the low end is cheaper and the top end costs disproportionately
#: more — carrying a star is meant to be a felt cost, not a rounding error.
_STRENGTH_EXPONENT = 2.0

#: The age band a salary is not penalised across. Reads the visible `age`
#: field only — never `peak_age`, which is hidden (riders/README.md,
#: Visible vs hidden). A rider outside this band costs up to
#: _AGE_PENALTY_MAX less, tapering linearly to the model's age limits
#: (18, 40) at the edges.
_PRIME_AGE_LOW = 24
_PRIME_AGE_HIGH = 32
_AGE_PENALTY_MAX = 0.15

#: The model's own age validators (riders/models.py) — duplicated here so
#: this module stays self-contained arithmetic, same reasoning as
#: staff/pricing.py's _SPECIALITY_BAND duplicating staff/generation.py's
#: band.
_MIN_AGE = 18
_MAX_AGE = 40

#: Smallest salary movement worth reporting to a manager (#26). The
#: formula rounds to the nearest 50, so 50 is the smallest change it can
#: produce at all; at 100 a rider must move two rounding steps, which
#: filters the drift `age_multiplier` alone produces at a birthday while
#: any real attribute movement still clears it. Filters the *report* only
#: — every rider's stored salary is always updated exactly (plan D4).
SALARY_REVIEW_THRESHOLD = 100


def _round_to_nearest_50(value: float) -> int:
    """Integer nearest-50 rounding, so prices read as prices rather than as
    hash output. Same helper as staff/pricing.py; duplicated rather than
    imported since riders/ may not import staff/ (AGENTS.md)."""
    return 50 * round(value / 50)


def strength(rider) -> float:
    """A rider's overall level on roughly the same 1-100 scale as a single
    attribute, weighting each of the five engine attributes by what the
    rider's speciality values (SPECIALITY_PROFILES) rather than taking a
    flat mean — a Climber's climb matters more to their price than their
    sprint, the same way it matters more to how they race."""
    profile = SPECIALITY_PROFILES[rider.speciality]
    weighted = sum(getattr(rider, name) * profile[name] for name in ENGINE_ATTRIBUTES)
    return weighted / sum(profile.values())


def age_multiplier(age: int) -> float:
    """1.0 across the prime years, tapering to `1 - _AGE_PENALTY_MAX` at
    the model's age limits. Mild by design (Design decision 4): visible
    strength is meant to dominate the price, not age."""
    if _PRIME_AGE_LOW <= age <= _PRIME_AGE_HIGH:
        return 1.0
    if age < _PRIME_AGE_LOW:
        fraction = (_PRIME_AGE_LOW - age) / (_PRIME_AGE_LOW - _MIN_AGE)
    else:
        fraction = (age - _PRIME_AGE_HIGH) / (_MAX_AGE - _PRIME_AGE_HIGH)
    fraction = max(0.0, min(1.0, fraction))
    return 1.0 - _AGE_PENALTY_MAX * fraction


def weekly_salary_for(rider) -> int:
    """This rider's weekly salary in whole credits. Pure: no database
    access, safe on an unsaved Rider."""
    scaled = max(0.0, min(1.0, strength(rider) / 100)) ** _STRENGTH_EXPONENT
    base = SALARY_AT_MIN_STRENGTH + (SALARY_AT_MAX_STRENGTH - SALARY_AT_MIN_STRENGTH) * scaled
    base *= age_multiplier(rider.age)
    return max(SALARY_AT_MIN_STRENGTH, _round_to_nearest_50(base))
