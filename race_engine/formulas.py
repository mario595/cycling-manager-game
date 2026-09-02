from __future__ import annotations

from race_engine.models import RiderAttributes

# Speed ranges (m/s) per terrain, mapped from attribute 1-100
# Flat:  8-16 m/s (29-58 km/h)
# Uphill: 2-11 m/s (7-40 km/h)
# Downhill: 12-25 m/s (43-90 km/h)

FLAT_MIN_SPEED = 8.0
FLAT_MAX_SPEED = 16.0
UPHILL_MIN_SPEED = 4.0
UPHILL_MAX_SPEED = 14.0
DOWNHILL_MIN_SPEED = 12.0
DOWNHILL_MAX_SPEED = 25.0

# Drafting
DRAFT_DISTANCE = 3.0  # meters behind a leader to benefit
DRAFT_ENERGY_DISCOUNT = 0.35  # fraction of energy drain saved while drafting
DRAFT_UPHILL_LIMIT = 5.0  # gradient % above which drafting is negligible

# Speed variability — small per-tick jitter (m/s peak) breaks perfect ties so
# groups form a realistic echelon (front rider pulls, rest draft).
SPEED_JITTER = 0.3

# Pacing cost — extra energy (per tick per m/s) a rider spends when forced to
# hold a pace above their own natural speed (i.e. matching a faster group).
# This models the physical cost of sitting on a wheel that's too fast for you.
PACING_COST = 0.005


def _lerp(min_val: float, max_val: float, t: float) -> float:
    """Linear interpolation. t in [0, 1]."""
    return min_val + (max_val - min_val) * t


def add_speed_jitter(speed: float) -> float:
    """Add small per-tick speed variation so riders don't stay perfectly tied."""
    import random

    jitter = random.uniform(-SPEED_JITTER, SPEED_JITTER)
    return max(1.0, speed + jitter)


def compute_base_speed(attributes: RiderAttributes, gradient: float) -> float:
    """Base speed in m/s from rider attributes and terrain gradient.

    Flat: flat attribute maps to [FLAT_MIN, FLAT_MAX] m/s.
    Uphill: climb attribute maps to [UPHILL_MIN, UPHILL_MAX], reduced by gradient.
    Downhill: sprint+flat blend maps to [DOWNHILL_MIN, DOWNHILL_MAX], boosted by gradient.
    """
    GRADIENT_PENALTY = 0.25  # speed loss per % gradient on uphills
    DESCENT_BOOST = 0.3  # speed gain per % gradient on downhills

    if gradient == 0:
        t = (attributes.flat - 1) / 99.0
        return _lerp(FLAT_MIN_SPEED, FLAT_MAX_SPEED, t)

    if gradient > 0:
        t = (attributes.climb - 1) / 99.0
        base = _lerp(UPHILL_MIN_SPEED, UPHILL_MAX_SPEED, t)
        penalty = gradient * GRADIENT_PENALTY
        return max(1.0, base - penalty)

    # gradient < 0
    t = ((attributes.sprint + attributes.flat) / 2.0 - 1) / 99.0
    base = _lerp(DOWNHILL_MIN_SPEED, DOWNHILL_MAX_SPEED, t)
    boost = abs(gradient) * DESCENT_BOOST
    return min(DOWNHILL_MAX_SPEED, base + boost)


def apply_energy_modifier(base_speed: float, energy: float, stamina: float) -> float:
    """Scale speed based on remaining energy and stamina."""
    ENERGY_THRESHOLD = 40.0
    STAMINA_THRESHOLD = 30.0

    energy_mod = 1.0
    if energy < ENERGY_THRESHOLD:
        energy_mod = 0.5 + 0.5 * (energy / ENERGY_THRESHOLD)

    stamina_mod = 1.0
    if stamina < STAMINA_THRESHOLD:
        stamina_mod = 0.6 + 0.4 * (stamina / STAMINA_THRESHOLD)

    return base_speed * energy_mod * stamina_mod


def draft_discount(gradient: float) -> float:
    """Energy-drain multiplier from drafting. 1.0 = no benefit (uphill)."""
    if gradient > DRAFT_UPHILL_LIMIT:
        return 1.0
    return 1.0 - DRAFT_ENERGY_DISCOUNT


def compute_pacing_drain(
    effective_speed: float, own_speed: float, resistance: int
) -> float:
    """Extra energy per tick from being forced to match a pace above natural.

    effective_speed is the group pace the rider is held at (>= own_speed when
    they are forced to ride faster than comfortable). Returns 0 when the rider
    is not overshooting their own pace.

    Scaled by resistance so a rider with better fatigue tolerance holds a fast
    wheel more cheaply than a fragile rider at the same overshoot.
    """
    RESISTANCE_FACTOR = 0.5
    overshoot = max(0.0, effective_speed - own_speed)
    resistance_mod = 1.0 - (resistance / 100.0) * RESISTANCE_FACTOR
    return PACING_COST * overshoot * resistance_mod


def compute_energy_drain(
    attributes: RiderAttributes,
    gradient: float,
    speed: float,
    draft: float = 1.0,
) -> float:
    """Energy consumed per tick. Higher on uphills, scales with speed.

    draft is the draft_discount multiplier (1.0 no drafting, <1.0 drafting).
    Positive drain is reduced by drafting; downhill recovery is left unchanged.
    """
    BASE_DRAIN_FLAT = 0.012
    CLIMB_MULTIPLIER = 3.0
    RECOVERY_DOWNHILL = 0.008
    RESISTANCE_FACTOR = 0.5
    SPEED_FACTOR = 0.008

    resistance_mod = 1.0 - (attributes.resistance / 100.0) * RESISTANCE_FACTOR
    speed_mod = 1.0 + (speed - 10.0) * SPEED_FACTOR

    if gradient > 0:
        return BASE_DRAIN_FLAT * CLIMB_MULTIPLIER * resistance_mod * speed_mod * draft
    elif gradient < 0:
        return -RECOVERY_DOWNHILL * (1.0 - resistance_mod * 0.5)

    return BASE_DRAIN_FLAT * resistance_mod * speed_mod * draft


def compute_stamina_drain(gradient: float, speed: float) -> float:
    """Stamina consumed per tick. Slow, steady drain. Faster uphill."""
    BASE_STAMINA_DRAIN = 0.004
    CLIMB_BONUS = 0.002

    if gradient > 0:
        return BASE_STAMINA_DRAIN + CLIMB_BONUS
    return BASE_STAMINA_DRAIN
