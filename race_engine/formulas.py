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
# Draft-shelter quality: bounded by positioning (skill) and how deep the rider
# sits. DEPTH_SATURATION is the pack depth at which full shelter is reached
# (rider ~10 wheels back is as sheltered as it gets). Bases keep a fixed
# fraction of drain while sheltered; the bonus deepens that save toward the
# floor for high-skill, deep-positioned riders.
DRAFT_DEPTH_SATURATION = 10.0  # wheels back at which shelter saturates
DRAFT_STAMINA_BASE = 0.85  # stamina keep-fraction while sheltered
DRAFT_STAMINA_FLOOR = 0.70  # best-possible stamina keep-fraction
DRAFT_ENERGY_BASE = 0.60  # energy cost keep-fraction while sheltered
DRAFT_ENERGY_FLOOR = 0.40  # best-possible energy cost keep-fraction
# DRAFT_HOLD_MAX: how much faster than their SOLO cruise a deeply sheltered,
# skilled rider can sustain in the group (the aero saving that lets a weaker
# rider hold the bunch's tempo on flats/moderate terrain). An exposed rider
# (depth 0) holds 1.0x their solo cruise and may be dropped.
DRAFT_HOLD_MAX = 1.30  # best-possible hold multiplier while fully sheltered
DRAFT_HOLD_MIN = 1.0  # exposed / no shelter

# Speed variability — small per-tick jitter (m/s peak) breaks perfect ties so
# groups form a realistic echelon (front rider pulls, rest draft).
SPEED_JITTER = 0.3

# Group-effort pacing — a sheltered pack rolls at a controlled sustainable
# tempo rather than each rider at their own maximal pace. Riders within
# PACK_COHESION_DISTANCE of each other on draft-allowed terrain cohere into a
# peloton and ride at the group tempo (a sustainable pace the able members can
# hold). GROUP_DROP_FRACTION is how far below the group's best cruise a rider
# may fall and still stay sheltered; below it the rider is dropped rather than
# the whole pack slowing down.
PACK_COHESION_DISTANCE = 60.0  # meters within which riders cohere into a pack
GROUP_DROP_FRACTION = 0.90

# Terrain classification — gradients are bucketed for the tactics engine.
TERRAIN_MODERATE_THRESHOLD = 3.0  # gradient % at which terrain becomes "moderate"
TERRAIN_STEEP_THRESHOLD = 7.0  # gradient % at which terrain becomes "steep"

# Race phases — defined by remaining distance as a fraction of total course
# length. Phase thresholds gate when attacks and chases are viable.
EARLY_PHASE_THRESHOLD = 0.25  # > 25% remaining → early (no attacking)
TRANSITION_PHASE_THRESHOLD = 0.10  # 10–25% remaining → transition
# < 10% remaining → finale

# Surge / attack / sprint reflexes — discrete energy-burst efforts.
SURGE_DURATION = 20  # ticks a single (non-sprint) effort lasts (~20s)
SURGE_COOLDOWN = 60  # ticks before a rider may surge again (~1min)
SURGE_SPEED_BOOST = 0.25  # fraction above cruise while surging
SURGE_ENERGY_COST = 0.05  # extra anaerobic energy burned per surge tick
SURGE_MIN_ENERGY = 30.0  # minimum energy to consider starting a surge
SPRINT_DISTANCE = 1000.0  # meters from the finish that triggers the final kick
SPRINT_DURATION = 40  # ticks a finish-sprint kick lasts (~40s), longer than a normal surge
SPRINT_MIN_SPRINT = 70.0  # sprint attribute needed to launch a finish sprint
SPRINT_MIN_ENERGY = 35.0  # minimum energy to launch a finish sprint (costs more)

# Attack reflex — phase-gated, terrain-gated (steep terrain = the STEEP bucket).
ATTACK_MIN_CLIMB = 75.0  # climb attribute needed to consider attacking
ATTACK_PHASE_THRESHOLD = 0.25  # only attack in transition + finale (< 25% remaining)

# Chase reflex — wider gap threshold than before, phase-gated.
CHASE_GAP_MAX = 30.0  # meters behind a leader to trigger a chase surge
CHASE_DISTANCE_MAX = 0.15  # only chase in final 15% of race
CHASE_MIN_ENERGY = 25.0  # minimum energy to initiate a chase
CHASE_MIN_CLIMB_ADVANTAGE = -10.0  # don't chase on steep if leader is 10+ climb points stronger


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


def compute_draft_factors(
    positioning: int, depth: float
) -> tuple[float, float]:
    """Draft keep-fractions for (stamina, energy) given shelter quality.

    ``positioning`` is the rider's draft skill (1-100); ``depth`` is how many
    riders shelter ahead of them in the pack (0 = pulling/exposed, no save).
    Quality blends positioning skill and pack depth, then maps base keep-
    fractions down toward their floors for fully sheltered, skilled riders.
    Returns fractions of drain/cost actually kept (lower = better shelter).
    """
    skill = (positioning - 1) / 99.0
    depth_factor = min(float(depth), DRAFT_DEPTH_SATURATION) / DRAFT_DEPTH_SATURATION
    quality = 0.6 * skill + 0.4 * depth_factor
    quality = max(0.0, min(1.0, quality))
    if depth < 1.0:
        return (1.0, 1.0)
    stamina = DRAFT_STAMINA_BASE - (DRAFT_STAMINA_BASE - DRAFT_STAMINA_FLOOR) * quality
    energy = DRAFT_ENERGY_BASE - (DRAFT_ENERGY_BASE - DRAFT_ENERGY_FLOOR) * quality
    return (stamina, energy)


def draft_hold_multiplier(positioning: int, depth: float, gradient: float) -> float:
    """How much faster than solo cruise a sheltered rider can hold the tempo.

    ``positioning`` is draft skill (1-100), ``depth`` how many riders shelter
    ahead in the pack (0 = front/exposed, no save), ``gradient`` the climb %.
    Reuses the same skill/depth quality blend as `compute_draft_factors` but
    maps it to a **speed multiplier** a rider can sustain in the wheels instead
    of a drain keep-fraction. Used by the pack-cohesion drop test so a weaker
    rider who is sheltering behind a strong group (e.g. a climber in the bunch
    on the flat) is not dropped just because their solo cruise is below the
    group tempo.

    The credit fades with gradient: drafting is hugely effective on flats (a
    sheltered rider holds far above their solo speed) but nearly useless on a
    sustained climb (drag matters little at climbing speeds, power-to-weight
    dominates), so on a steep gradient a weak climber is no longer protected.
    """
    if depth < 1.0:
        return DRAFT_HOLD_MIN
    skill = (positioning - 1) / 99.0
    depth_factor = min(float(depth), DRAFT_DEPTH_SATURATION) / DRAFT_DEPTH_SATURATION
    quality = 0.6 * skill + 0.4 * depth_factor
    quality = max(0.0, min(1.0, quality))
    drag = 1.0 - min(1.0, max(0.0, gradient) / DRAFT_UPHILL_LIMIT)
    return DRAFT_HOLD_MIN + (DRAFT_HOLD_MAX - DRAFT_HOLD_MIN) * quality * drag


def compute_energy_drain(
    gradient: float,
    effective_speed: float,
    own_speed: float,
    draft_energy_factor: float = 1.0,
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

    overshoot = max(0.0, effective_speed - own_speed)
    intensity = overshoot * BURST_FACTOR

    if draft_energy_factor < 1.0:
        intensity *= draft_energy_factor

    if intensity > 0:
        return intensity
    return -RECOVERY


def compute_stamina_drain(
    gradient: float,
    speed: float,
    draft_stamina_factor: float = 1.0,
    resistance: int = 50,
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

    drain = BASE * (1.0 + (speed - 10.0) * SPEED_FACTOR)
    drain *= 1.0 - (resistance / 100.0) * RESISTANCE_FACTOR

    if draft_stamina_factor < 1.0:
        drain *= draft_stamina_factor

    if gradient > 0:
        drain *= 1.0 + gradient * GRADIENT_SCALE
    elif gradient < 0:
        drain -= DESCENT_RECOVERY

    return drain
