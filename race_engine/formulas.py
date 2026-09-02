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
DRAFT_UPHILL_LIMIT = 5.0  # gradient % above which drafting is negligible

# Speed variability — small per-tick jitter (m/s peak) breaks perfect ties so
# groups form a realistic echelon (front rider pulls, rest draft).
SPEED_JITTER = 0.3

# Surge / attack / sprint reflexes — discrete energy-burst efforts.
SURGE_DURATION = 20  # ticks a single effort lasts (~20s)
SURGE_COOLDOWN = 60  # ticks before a rider may surge again (~1min)
SURGE_SPEED_BOOST = 0.25  # fraction above cruise while surging
SURGE_ENERGY_COST = 0.05  # extra anaerobic energy burned per surge tick
SURGE_MIN_ENERGY = 30.0  # minimum energy to consider starting a surge
SPRINT_DISTANCE = 1000.0  # meters from the finish that triggers the final kick
SPRINT_MIN_SPRINT = 70.0  # sprint attribute needed to launch a finish sprint
ATTACK_MIN_GRADIENT = 6.0  # climb % at which a climber may attack
ATTACK_MIN_CLIMB = 75.0  # climb attribute needed to consider attacking
CHASE_GAP_THRESHOLD = 8.0  # meters behind a leader to trigger a chase surge


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


def apply_stamina_cruise_modifier(base_speed: float, stamina: float) -> float:
    """Scale base cruising speed by remaining stamina (progressive cracking).

    A rider's sustainable cruise pace degrades smoothly as stamina depletes, so
    tired riders crack progressively in the finale rather than only once below
    a hard threshold.
    """
    STAMINA_CRACK_ZONE = 60.0  # degradation begins below this
    if stamina >= STAMINA_CRACK_ZONE:
        return base_speed
    frac = max(0.0, stamina / STAMINA_CRACK_ZONE)
    return base_speed * (frac**0.7)


def apply_energy_burst_modifier(base_speed: float, energy: float) -> float:
    """Scale burst power by remaining energy (short-term anaerobic reserve).

    Low energy caps how hard a rider can surge (climb/attack/sprint) without
    throttling steady cruising, which is governed by stamina.
    """
    ENERGY_THRESHOLD = 40.0
    if energy >= ENERGY_THRESHOLD:
        return base_speed
    return base_speed * (0.5 + 0.5 * (energy / ENERGY_THRESHOLD))


def compute_energy_drain(
    gradient: float,
    effective_speed: float,
    own_speed: float,
    drafting: bool,
) -> float:
    """Anaerobic energy consumed per tick — only spent under high intensity.

    Energy is a short-term burst reserve. It drains only when a rider works
    above their own sustainable cruise (the overshoot between the group/forced
    pace and their natural pace), and recovers when cruising or descending.
    Steady climbing stresses stamina, not energy, so sustained effort won't
    empty the anaerobic reserve. Drafting conserves energy so a rider sitting
    in the wheels preserves it for an attack or the finish.
    """

    BURST_FACTOR = 0.10  # energy cost per m/s held above your own cruise
    RECOVERY = 0.008  # energy recovered per tick while cruising/descending
    DRAFT_SAVING = 0.6  # fraction of burst cost retained while drafting

    overshoot = max(0.0, effective_speed - own_speed)
    intensity = overshoot * BURST_FACTOR

    if drafting:
        intensity *= DRAFT_SAVING

    if intensity > 0:
        return intensity
    return -RECOVERY


def compute_stamina_drain(
    gradient: float,
    speed: float,
    drafting: bool,
    resistance: int,
) -> float:
    """Aerobic stamina consumed per tick — cumulative long-distance endurance.

    Depletes steadily with total rolling workload: faster pace and steeper
    climbs burn more, high resistance (fatigue tolerance) slows it, drafting
    conserves it, and descents offer a small recovery. Stamina responds slowly
    and is the meter that decides whether a rider cracks in the finale.
    """
    BASE = 0.012
    SPEED_FACTOR = 0.010  # more aerobic load per m/s above 10 m/s cruise
    RESISTANCE_FACTOR = 0.6  # fatigue tolerance's protection
    GRADIENT_SCALE = 0.20  # extra load multiplier per % climb
    DESCENT_RECOVERY = 0.006
    DRAFT_FACTOR = 0.85  # conserve stamina in the wheels

    drain = BASE * (1.0 + (speed - 10.0) * SPEED_FACTOR)
    drain *= 1.0 - (resistance / 100.0) * RESISTANCE_FACTOR

    if drafting:
        drain *= DRAFT_FACTOR

    if gradient > 0:
        drain *= 1.0 + gradient * GRADIENT_SCALE
    elif gradient < 0:
        drain -= DESCENT_RECOVERY

    return drain
