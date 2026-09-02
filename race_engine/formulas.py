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


def _lerp(min_val: float, max_val: float, t: float) -> float:
    """Linear interpolation. t in [0, 1]."""
    return min_val + (max_val - min_val) * t


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


def compute_energy_drain(
    attributes: RiderAttributes, gradient: float, speed: float
) -> float:
    """Energy consumed per tick. Higher on uphills, scales with speed."""
    BASE_DRAIN_FLAT = 0.012
    CLIMB_MULTIPLIER = 3.0
    RECOVERY_DOWNHILL = 0.008
    RESISTANCE_FACTOR = 0.5
    SPEED_FACTOR = 0.008

    resistance_mod = 1.0 - (attributes.resistance / 100.0) * RESISTANCE_FACTOR
    speed_mod = 1.0 + (speed - 10.0) * SPEED_FACTOR

    if gradient > 0:
        return BASE_DRAIN_FLAT * CLIMB_MULTIPLIER * resistance_mod * speed_mod
    elif gradient < 0:
        return -RECOVERY_DOWNHILL * (1.0 - resistance_mod * 0.5)

    return BASE_DRAIN_FLAT * resistance_mod * speed_mod


def compute_stamina_drain(gradient: float, speed: float) -> float:
    """Stamina consumed per tick. Slow, steady drain. Faster uphill."""
    BASE_STAMINA_DRAIN = 0.004
    CLIMB_BONUS = 0.002

    if gradient > 0:
        return BASE_STAMINA_DRAIN + CLIMB_BONUS
    return BASE_STAMINA_DRAIN
