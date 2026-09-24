from __future__ import annotations

import math
import random
from typing import Any

from race_engine.models import RiderAttributes, Terrain, WindState

# Terrain speed is a per-rider power balance rather than three disjoint
# lookup tables: K_aero*v**3 + (K_roll + K_grav*s)*v = 1, where s is gradient
# as a fraction. `flat` decides K_aero/K_roll (power-to-drag), `climb` decides
# K_grav (power-to-weight) via a second anchor at CLIMB_REF_GRADIENT, and the
# blend between them falls out of the equation rather than being a tuning
# curve — see `compute_base_speed` and README.md's "Terrain speed" section.
#
# Solo speeds at the two calibration anchors, mapped from attribute 1-100:
# flat (gradient 0): 12.0-14.2 m/s (43.2-51.1 km/h)
# climb (gradient 8%): 3.5-6.1 m/s (12.6-22.0 km/h)
# downhill handling cap: 17.0-21.0 m/s (61-76 km/h)
FLAT_MIN_SPEED = 12.0
FLAT_MAX_SPEED = 14.2
CLIMB_MIN_SPEED = 3.5
CLIMB_MAX_SPEED = 6.1
DOWNHILL_MIN_SPEED = 17.0
DOWNHILL_MAX_SPEED = 21.0
AERO_SHARE = 0.85  # fraction of flat resistance that is aero drag (vs. rolling)
CLIMB_REF_GRADIENT = 0.08  # gradient (fraction) the climb anchor is calibrated at

# Drafting
DRAFT_DISTANCE = 3.0  # meters behind a leader to benefit
DRAFT_UPHILL_LIMIT = 5.0  # gradient % above which drafting is negligible
# Draft-shelter quality: bounded by positioning (skill) and how deep the rider
# sits. DEPTH_SATURATION is the pack depth at which full shelter is reached
# (rider ~10 wheels back is as sheltered as it gets). Shelter feeds the engine
# through exactly one channel — DRAFT_HOLD_MAX below, the speed a sheltered
# rider holds for free — and both fatigue meters measure effort against that
# speed. There are deliberately no separate stamina/energy keep-fractions:
# crediting shelter twice is what previously bled sheltered riders dry.
DRAFT_DEPTH_SATURATION = 10.0  # wheels back at which shelter saturates
# DRAFT_HOLD_MAX: how much faster than their SOLO cruise a deeply sheltered,
# skilled rider can sustain in the group (the aero saving that lets a weaker
# rider hold the bunch's tempo on flats/moderate terrain). An exposed rider
# (depth 0) holds 1.0x their solo cruise and may be dropped.
DRAFT_HOLD_MAX = 1.30  # best-possible hold multiplier while fully sheltered
DRAFT_HOLD_MIN = 1.0  # exposed / no shelter

# Rotation-averaged shelter — for the pack-cohesion drop test and the fatigue
# reference ONLY (not the `pulling` display flag, which is exactly "at the
# front of a pack this tick" and needs no averaging). Real bunches
# rotate, so nobody rides a whole race at their instantaneous depth; using raw
# instantaneous depth charges whoever is a half-wheel ahead this tick as fully
# exposed and lets a jitter tick shed them. ROTATION_SHARE floors effective
# depth at this fraction of (pack_size - 1), i.e. every rider is credited with
# at least "sometimes near the front, sometimes not" shelter rather than only
# their current position.
#
# Role-scaled (Tier A2, TEAM_TACTICS_PLAN.md): a team's support riders take
# more than their share of time at depth 0 and a leader less, so the original
# single constant (0.5, the role-blind average) becomes two — support riders
# get a lower floor (they really are more often at the front, less shelter
# credit), a protected leader a higher one (rotation credits them as being
# near the front less often than they physically are). A leader physically
# at the front still pulls this tick — this biases the *rotation average*
# the fatigue formulas see, not the pack geometry. A solo rider (team of
# one, `role` defaults to "leader") uses ROTATION_SHARE_LEADER — with no
# teammates to hand shelter to, this is the same generous end of the old
# single-constant behavior riders always had.
ROTATION_SHARE_LEADER = 0.65
ROTATION_SHARE_SUPPORT = 0.35

# Teammate shelter priority (Tier A1, TEAM_TACTICS_PLAN.md): a rider directly
# behind a *teammate*'s wheel gets a modest bonus to effective depth, on top
# of the existing gap-decayed value — real teams hand each other wheels and
# ride as a deliberate unit; strangers in a pack merely happen to be near
# each other. Added to eff_depth (not multiplied) so it matters most for a
# rider already close enough to be credited at all (gap_factor > 0) and does
# nothing for one too far off the wheel to be sheltered regardless of who is
# up there. Kept small: this stacks with A2's leader-favoring rotation floor,
# and an over-tuned combination would make whoever is named leader
# untouchable (see TEAM_TACTICS_PLAN.md's Risks).
TEAMMATE_SHELTER_BONUS = 1.0

# Speed variability — small per-tick jitter (m/s peak) breaks perfect ties so
# groups form a realistic echelon (front rider pulls, rest draft).
SPEED_JITTER = 0.3

# Group-effort pacing — a sheltered pack rolls at a controlled tempo *chosen
# for the race situation*, not at a fixed fraction of the strongest rider's
# ceiling. Riders within PACK_COHESION_DISTANCE of each other on draft-allowed
# terrain cohere into a peloton and ride at that tempo; a rider whose
# drafting-credited cruise falls below it is dropped rather than the whole pack
# slowing down.
#
# The tempo fraction is situational, because a real bunch only rides near its
# ceiling when it has a reason to: on a flat opening hour with nobody up the
# road the peloton rolls, it lifts through the transition phase, and it goes
# full gas only in the finale or while chasing a rider who is clear.
PACK_COHESION_DISTANCE = 60.0  # meters within which riders cohere into a pack
PACK_TEMPO_EASY = 0.75  # early + flat + nobody up the road — rolling tempo
PACK_TEMPO_STEADY = 0.82  # transition phase, or early on climbing terrain
PACK_TEMPO_HARD = 0.90  # finale, or chasing a rider who is clear
# A rotating, drafting bunch shares the wind and so is faster than any solo
# rider on the flat — real breaks get caught for exactly this reason. Above
# DRAFT_UPHILL_LIMIT there's no wind to share, so the chase falls back to
# PACK_TEMPO_HARD. Depends on rotation-averaged shelter (see ROTATION_SHARE_LEADER)
# so the pack doesn't shed riders one at a time from the front while chasing
# above 1.0x the pace-setter reference.
PACK_TEMPO_CHASE = 1.08
# How far ahead of a pack's front rider someone must be to count as "clear up
# the road", which makes the pack chase at PACK_TEMPO_HARD/PACK_TEMPO_CHASE.
BREAK_CLEAR_DISTANCE = 60.0

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
SURGE_SPEED_BOOST = 0.25  # fraction above cruise while surging (attack/chase)
SURGE_ENERGY_COST = 0.05  # extra anaerobic energy burned per surge tick
SURGE_MIN_ENERGY = 30.0  # minimum energy to consider starting a surge
SPRINT_DISTANCE = 1000.0  # meters from the finish that triggers the final kick
SPRINT_DURATION = 40  # ticks a finish-sprint kick lasts (~40s), longer than a normal surge
SPRINT_MIN_ENERGY = 35.0  # minimum energy to launch a finish sprint (costs more)
# Finish-sprint boost scales with `sprint` rather than gating eligibility at a
# threshold — everyone kicks in the last km, a weak sprinter's kick is just
# worth less. Replaces the old flat SURGE_SPEED_BOOST for sprints specifically.
SPRINT_BOOST_MIN = 0.05  # kick size for the weakest possible sprint attribute
SPRINT_BOOST_MAX = 0.35  # kick size for the strongest possible sprint attribute

# Attack reflex — phase-gated, terrain-gated (steep terrain = the STEEP bucket).
ATTACK_MIN_CLIMB = 75.0  # climb attribute needed to consider attacking
ATTACK_PHASE_THRESHOLD = 0.25  # only attack/bridge in transition + finale (< 25% remaining)

# Bridge (chase) reflex — a rider joins a genuinely clear move, not any gap.
# "Clear" reuses BREAK_CLEAR_DISTANCE (above), the same test pack tempo uses
# to decide whether the bunch is chasing something real, so a strung-out pack
# doesn't read as eleven simultaneous breakaways.
BRIDGE_GAP_MAX = 150.0  # meters to a clear break still worth bridging to
BRIDGE_MAX_DEPTH = 2  # only the front of a group considers bridging
CHASE_MIN_ENERGY = 25.0  # minimum energy to initiate a bridge/chase
CHASE_MIN_CLIMB_ADVANTAGE = -10.0  # don't chase on steep if leader is 10+ climb points stronger

# Time cut (broom wagon) — once the winner finishes, the fraction of their
# time after which the race closes; anyone still on the road is DNF.
# Calibrated against race_engine/audit.py's six bundled configs (default 5
# seeds): mountain_stage's sprinters — negligible climb, minimal draft
# credit on sustained gradient — legitimately finish up to 37.6% behind the
# winner (last_over_winner_ratio 1.3756, seed 2024; every other bundled
# config's worst straggler, and grand_field's, stay under 9% and 37.6%
# respectively). The worst clean ratio observed across 13 seeds of a
# larger, issue-#102-shaped field (32 riders, doubled roster, 200 km) was
# 1.44. 0.5 clears all of that with room to spare while still cutting
# #102's own reported spike (ratio 1.868) at 1.5x instead of letting it run
# to 1.868x — a real cut, not just a technically-compliant one. 0.25 (this
# constant's very first, placeholder value, assuming a ~10% clean spread)
# would have cut the clean races above; do not go back below 0.5 without
# re-running the audit against all six bundled configs and grand_field.
TIME_CUT_MARGIN = 0.5

# Wind (Tier A: attrition only — see race_engine/WIND_PLAN.md). Modelled
# relative to the rider (0=head, 90=from the right, 180=tail, 270=from the
# left), never as a compass bearing. Enters the physics through the aero
# term of compute_base_speed only.
WIND_V_REF = 13.1  # m/s reference speed for apparent-wind calc (fixed, not live rider speed)
WIND_K_CROSS = 0.45  # how much a crosswind component adds to apparent wind
WIND_TAILWIND_EFFICIENCY = 0.55  # only this fraction of a tailwind's along-course component counts
WIND_AERO_MULT_MIN = 0.55
WIND_AERO_MULT_MAX = 2.20

WIND_BANDS: dict[str, dict[str, Any]] = {
    "calm": {"probability": 0.45, "mean_range": (0.0, 6.0)},
    "light": {"probability": 0.30, "mean_range": (6.0, 14.0)},
    "moderate": {"probability": 0.18, "mean_range": (14.0, 24.0)},
    "strong": {"probability": 0.07, "mean_range": (24.0, 38.0)},
}

WIND_SPEED_RETARGET_PROB = 0.002  # chance per tick the intensity target is re-rolled
WIND_SPEED_RELAX = 0.004  # fraction of the way current speed moves to target, per tick
WIND_ANGLE_TURN_PROB = 0.0008  # chance per tick of a sharp swing (road turning)
WIND_ANGLE_TURN_RANGE = (60.0, 140.0)  # degrees, magnitude of a sharp swing
WIND_ANGLE_MEANDER_SIGMA = 0.15  # degrees, stddev of the continuous meander per tick
WIND_ANGLE_RELAX = 0.01  # fraction of the way current angle moves to target, per tick


def wind_aero_multiplier(wind_speed_kmh: float, angle_deg: float) -> float:
    """Aero-drag multiplier from wind speed/angle, relative to the rider.

    Uses a fixed WIND_V_REF rather than the rider's live speed — using live
    speed would make the multiplier re-entrant with the power-balance solver
    (speed depends on drag depends on speed) and would break the solver's
    memoisation. A tailwind's along-course component is discounted by
    WIND_TAILWIND_EFFICIENCY (a rider spins out their gearing and still pays
    rolling resistance; they don't convert the whole tailwind into speed) —
    without it, apparent wind loss lets speed run away downwind. See
    WIND_PLAN.md decision 4 for the verified effect table this reproduces.
    """
    w = wind_speed_kmh / 3.6
    along = w * math.cos(math.radians(angle_deg))
    if along < 0:
        along *= WIND_TAILWIND_EFFICIENCY
    cross = abs(w * math.sin(math.radians(angle_deg)))
    apparent = math.sqrt((WIND_V_REF + along) ** 2 + (WIND_K_CROSS * cross) ** 2)
    mult = (apparent / WIND_V_REF) ** 2
    return max(WIND_AERO_MULT_MIN, min(WIND_AERO_MULT_MAX, mult))


def advance_wind(wind: WindState, rng: random.Random) -> None:
    """Drift wind speed and angle one tick, in place. Never assigns directly.

    Both intensity and angle relax exponentially toward a target
    (Ornstein-Uhlenbeck-style), which is what guarantees wind never jumps —
    there is no code path here that sets `speed`/`angle` outright. Angle
    additionally meanders continuously and occasionally takes a sharp swing
    (the road turning), moving along the shorter arc toward its target so a
    359->1 degree wrap doesn't spin the long way around.

    `rng` must be wind's own decorrelated substream (see
    `RaceState.create_initial_state`) — never the global `random` module,
    which `add_speed_jitter` also draws from.
    """
    if rng.random() < WIND_SPEED_RETARGET_PROB:
        spread = wind.band_mean * 0.5
        wind.target_speed = max(0.0, rng.uniform(wind.band_mean - spread, wind.band_mean + spread))
    wind.speed = max(0.0, wind.speed + (wind.target_speed - wind.speed) * WIND_SPEED_RELAX)

    wind.target_angle += rng.gauss(0.0, WIND_ANGLE_MEANDER_SIGMA)
    if rng.random() < WIND_ANGLE_TURN_PROB:
        magnitude = rng.uniform(*WIND_ANGLE_TURN_RANGE)
        wind.target_angle += magnitude if rng.random() < 0.5 else -magnitude

    delta = ((wind.target_angle - wind.angle + 180.0) % 360.0) - 180.0
    wind.angle = (wind.angle + delta * WIND_ANGLE_RELAX) % 360.0


def _lerp(min_val: float, max_val: float, t: float) -> float:
    """Linear interpolation. t in [0, 1]."""
    return min_val + (max_val - min_val) * t


def add_speed_jitter(speed: float) -> float:
    """Add small per-tick speed variation so riders don't stay perfectly tied."""
    import random

    jitter = random.uniform(-SPEED_JITTER, SPEED_JITTER)
    return max(1.0, speed + jitter)


def _rider_resistance_coeffs(attributes: RiderAttributes) -> tuple[float, float, float]:
    """Derive (K_aero, K_roll, K_grav) for a rider from two calibration anchors.

    v_flat is the rider's solo speed on the flat (from `flat`); v_climb8 is
    their solo speed at CLIMB_REF_GRADIENT (from `climb`). Aero drag is
    AERO_SHARE of flat resistance, rolling resistance the rest; the gravity
    coefficient is whatever makes the same equation solve to v_climb8 at the
    reference gradient.
    """
    t_flat = (attributes.flat - 1) / 99.0
    t_climb = (attributes.climb - 1) / 99.0
    v_flat = _lerp(FLAT_MIN_SPEED, FLAT_MAX_SPEED, t_flat)
    v_climb8 = _lerp(CLIMB_MIN_SPEED, CLIMB_MAX_SPEED, t_climb)

    k_aero = AERO_SHARE / v_flat**3
    k_roll = (1.0 - AERO_SHARE) / v_flat
    k_grav = (1.0 - k_roll * v_climb8 - k_aero * v_climb8**3) / (
        CLIMB_REF_GRADIENT * v_climb8
    )
    return k_aero, k_roll, k_grav


def _solve_power_balance(k_aero: float, k_roll: float, k_grav: float, s: float) -> float:
    """Solve K_aero*v**3 + (K_roll + K_grav*s)*v = 1 for v by bisection.

    Monotone increasing in v whenever K_roll + K_grav*s > 0 (true for every
    gradient a rider can face on these courses), so bisection converges
    reliably without needing a closed-form cubic solution.
    """
    lo, hi = 0.1, 40.0
    for _ in range(60):
        mid = (lo + hi) / 2.0
        value = k_aero * mid**3 + (k_roll + k_grav * s) * mid - 1.0
        if value < 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


_RESISTANCE_COEFF_CACHE: dict[tuple[int, int], tuple[float, float, float]] = {}
_POWER_BALANCE_CACHE: dict[tuple[int, int, float, float], float] = {}


def _attributes_key(attributes: RiderAttributes) -> tuple[int, int]:
    # Only flat/climb feed the coefficients; keying on those two (rather than
    # id(attributes)) is both sufficient and safe against attribute objects
    # being garbage-collected and their id() reused across separate races
    # (e.g. the audit harness running many races in one process).
    return (attributes.flat, attributes.climb)


def compute_base_speed(
    attributes: RiderAttributes, gradient: float, aero_mult: float = 1.0
) -> float:
    """Base speed in m/s from rider attributes, terrain gradient, and wind.

    A single power-balance model (see the module docstring above) replaces
    the old three disjoint speed tables: `flat` and `climb` become
    power-to-drag and power-to-weight, and everything in between (including
    the crossover right at gradient 0) falls out of the equation. Downhill
    speed uses the same equation, then applies a handling cap (cornering and
    braking, not power, limit a real descent).

    `aero_mult` (see `wind_aero_multiplier`) scales K_aero only, so wind
    fades on climbs automatically — the same equation that blends flat/climb
    terrain correctly does this for free, with no gradient special-casing.
    Defaults to 1.0 (no wind) so every pre-wind call site is unaffected.

    Memoised per (flat, climb, gradient, aero_mult): gradients are per-segment
    constants, so this is a few dozen solves per race. `aero_mult` is
    quantised to 2 decimal places in the cache key — wind changes
    continuously, so caching the raw float would make the cache grow
    unboundedly and never hit. A 1% error in drag is far below the model's
    per-tick jitter noise floor.
    """
    attrs_key = _attributes_key(attributes)
    coeffs = _RESISTANCE_COEFF_CACHE.get(attrs_key)
    if coeffs is None:
        coeffs = _rider_resistance_coeffs(attributes)
        _RESISTANCE_COEFF_CACHE[attrs_key] = coeffs
    k_aero, k_roll, k_grav = coeffs
    k_aero *= aero_mult

    s = gradient / 100.0
    cache_key = (attrs_key[0], attrs_key[1], gradient, round(aero_mult, 2))
    v = _POWER_BALANCE_CACHE.get(cache_key)
    if v is None:
        v = _solve_power_balance(k_aero, k_roll, k_grav, s)
        _POWER_BALANCE_CACHE[cache_key] = v

    if gradient >= 0:
        return v

    t_blend = ((attributes.sprint + attributes.flat) / 2.0 - 1) / 99.0
    cap = _lerp(DOWNHILL_MIN_SPEED, DOWNHILL_MAX_SPEED, t_blend)
    return min(v, cap)


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


def pace_setter_speed(member_speeds: list[float]) -> float:
    """Robust reference cruise for a pack's tempo.

    Taking ``max()`` lets a single jittered outlier dictate the tempo for the
    whole bunch and makes the pace jump around tick to tick. The median of the
    strongest third is stable and reflects the group's collective strength
    rather than one rider's best second.
    """
    if not member_speeds:
        return 0.0
    ordered = sorted(member_speeds, reverse=True)
    top = ordered[: max(1, len(ordered) // 3)]
    return top[len(top) // 2]


def pack_tempo_fraction(
    remaining_fraction: float,
    terrain: Terrain,
    chase_willingness: float,
    gradient: float,
) -> float:
    """Fraction of the pace-setter's cruise the pack chooses to ride at.

    A rotating, drafting bunch shares the wind and so outruns any solo rider
    on the flat — that is why flat breaks get caught — so a genuinely clear
    break on draftable terrain pushes the chase above even the finale's
    PACK_TEMPO_HARD. Above DRAFT_UPHILL_LIMIT there is no wind to share
    (power-to-weight dominates, not drag), so the chase falls back to
    PACK_TEMPO_HARD and a climber who goes clear on a real climb stays away.
    Otherwise: full gas in the finale, a steady tempo through the transition
    phase and on early climbing terrain, and a rolling pace on an early flat
    road where nobody is pushing.

    ``chase_willingness`` (0-1, Tier A3) is the fraction of the pack that
    sees a break worth chasing — a rider whose own teammate is the one clear
    up the road sits out, since chasing down your own break helps nobody.
    0.0 behaves exactly as "no break ahead"; 1.0 as "everyone agrees a break
    is on" (the old boolean's True). Anything between interpolates the chase
    tempo down rather than snapping between the two — a team with a rider
    away doesn't single-handedly stop the whole bunch from chasing, but it
    does genuinely blunt the chase in proportion to how many riders are
    still willing.
    """
    baseline = _pack_tempo_fraction_no_break(remaining_fraction, terrain)
    if chase_willingness <= 0.0:
        return baseline
    chase_target = (
        PACK_TEMPO_CHASE if gradient <= DRAFT_UPHILL_LIMIT else PACK_TEMPO_HARD
    )
    chase_target = max(chase_target, PACK_TEMPO_HARD if remaining_fraction < TRANSITION_PHASE_THRESHOLD else chase_target)
    return _lerp(baseline, chase_target, min(1.0, chase_willingness))


def _pack_tempo_fraction_no_break(remaining_fraction: float, terrain: Terrain) -> float:
    """The tempo fraction with nobody clear up the road worth chasing."""
    if remaining_fraction < TRANSITION_PHASE_THRESHOLD:
        return PACK_TEMPO_HARD
    if remaining_fraction < EARLY_PHASE_THRESHOLD:
        return PACK_TEMPO_STEADY
    if terrain is Terrain.FLAT:
        return PACK_TEMPO_EASY
    return PACK_TEMPO_STEADY


def compute_pack_tempo(
    member_speeds: list[float],
    remaining_fraction: float,
    terrain: Terrain,
    chase_willingness: float,
    gradient: float,
) -> float:
    """The shared speed a coherent pack rolls at this tick."""
    return pace_setter_speed(member_speeds) * pack_tempo_fraction(
        remaining_fraction, terrain, chase_willingness, gradient
    )


def shelter_quality(positioning: int, depth: float) -> float:
    """How good a rider's shelter is, 0-1, from draft skill and pack depth.

    ``positioning`` is the rider's draft skill (1-100); ``depth`` is how many
    riders shelter ahead of them in the pack (0 = pulling/exposed, no save).
    ``depth`` here is not necessarily the raw ordinal rank — the caller
    (`RaceState.tick`) folds in rotation-averaging and gap-decay (physical
    distance to the wheel ahead: real drafting benefit falls off sharply past
    a few meters) before calling this, so a rider two wheels back on paper
    but far off the wheel ahead is credited with much less than a full two
    wheels of shelter.
    """
    skill = (positioning - 1) / 99.0
    depth_factor = min(float(depth), DRAFT_DEPTH_SATURATION) / DRAFT_DEPTH_SATURATION
    return max(0.0, min(1.0, 0.6 * skill + 0.4 * depth_factor))


def draft_hold_multiplier(positioning: int, depth: float, gradient: float) -> float:
    """How much faster than solo cruise a sheltered rider can hold the tempo.

    ``positioning`` is draft skill (1-100), ``depth`` how many riders shelter
    ahead in the pack (0 = front/exposed, no save; see `shelter_quality`'s
    docstring — this is gap-decayed and rotation-averaged, not raw ordinal
    rank), ``gradient`` the climb %. Reuses the same skill/depth quality blend
    as `shelter_quality` but maps it to a **speed multiplier** a rider can
    sustain in the wheels instead of a drain keep-fraction. Used by the
    pack-cohesion drop test so a weaker rider who is sheltering behind a
    strong group (e.g. a climber in the bunch on the flat) is not dropped
    just because their solo cruise is below the group tempo.

    The credit fades with gradient: drafting is hugely effective on flats (a
    sheltered rider holds far above their solo speed) but nearly useless on a
    sustained climb (drag matters little at climbing speeds, power-to-weight
    dominates), so on a steep gradient a weak climber is no longer protected.
    """
    if depth < 1.0:
        return DRAFT_HOLD_MIN
    quality = shelter_quality(positioning, depth)
    drag = 1.0 - min(1.0, max(0.0, gradient) / DRAFT_UPHILL_LIMIT)
    return DRAFT_HOLD_MIN + (DRAFT_HOLD_MAX - DRAFT_HOLD_MIN) * quality * drag


def compute_energy_drain(
    effective_speed: float,
    sustainable_speed: float,
) -> float:
    """Anaerobic energy consumed per tick — only spent above what the rider can
    actually sustain *in the position they are riding*.

    ``sustainable_speed`` is the rider's draft-credited cruise: their own cruise
    when exposed or alone, and a higher speed when sheltered in a pack (see
    `draft_hold_multiplier`). Riding at or below it is free and recovers the
    reserve — sitting in the wheels at the bunch's tempo costs no matches, which
    is the entire point of shelter. Energy is burned only by the overshoot above
    it: surging, or hanging on to a pace the shelter cannot buy.

    Measuring against the *same* reference the pack-cohesion drop test uses
    keeps the two consistent. Charging overshoot against the solo cruise while
    the drop test credited the sheltered cruise meant a rider the engine said
    could hold the tempo was simultaneously bled dry for holding it.

    Steady climbing stresses stamina, not energy, so sustained effort won't
    empty the anaerobic reserve.
    """

    BURST_FACTOR = 0.10  # energy cost per m/s held above your sustainable pace
    RECOVERY = 0.008  # energy recovered per tick while within your means

    overshoot = max(0.0, effective_speed - sustainable_speed)
    intensity = overshoot * BURST_FACTOR

    if intensity > 0:
        return intensity
    return -RECOVERY


def compute_stamina_drain(
    gradient: float,
    speed: float,
    sustainable_speed: float,
    resistance: int = 50,
) -> float:
    """Aerobic stamina consumed per tick — cumulative long-distance endurance.

    Charged on **relative intensity**, not on wall-clock time: how hard the
    rider is working as a fraction of the pace they can sustain in the position
    they are riding (`sustainable_speed`, the same draft-credited reference the
    cohesion drop test and `compute_energy_drain` use). Intensity 1.0 is riding
    at your limit and costs BASE; the cubic exponent means an easy bunch tempo
    costs a small fraction of that, while hanging on above your means costs
    steeply more.

    This is what makes soft-pedalling in the wheels genuinely restful. With a
    flat per-second drain, slowing the peloton down made a race *more* tiring
    (more seconds on the road at near-identical cost per second), which is
    backwards — and it cracked exactly the low-`resistance` riders who should
    be conserving best in a sheltered bunch.

    High `resistance` (fatigue tolerance) slows the drain, climbs multiply it,
    and descents offer a small recovery. Stamina responds slowly and is the
    meter that decides whether a rider cracks in the finale.

    Drain is scaled by ``speed / DRAIN_REFERENCE_SPEED``: fatigue is
    fundamentally a cost of *distance covered* at a given relative effort, not
    of wall-clock ticks. Without this, `compute_base_speed`'s resistance model
    (see its docstring) — which correctly makes climbing roughly half as fast
    as the old disjoint speed tables — would double a climb's tick count and
    therefore double its stamina cost even at intensity 1.0 (a rider riding
    exactly their own sustainable climbing pace, no overshoot at all), cracking
    riders who are doing nothing wrong. DRAIN_REFERENCE_SPEED is the old
    model's mid-flat speed, which the new model's mid-flat speed still matches
    closely, so flat-terrain drain is essentially unchanged and only climbs
    (where speed drops sharply) scale down.
    """
    BASE = 0.012  # drain per tick at intensity 1.0, reference speed, riding at your limit
    INTENSITY_EXPONENT = 3.0  # aerobic cost rises steeply with relative effort
    RESISTANCE_FACTOR = 0.6  # fatigue tolerance's protection
    GRADIENT_SCALE = 0.20  # extra load multiplier per % climb
    DESCENT_RECOVERY = 0.006
    DRAIN_REFERENCE_SPEED = 13.4  # m/s — old mid-flat speed BASE was calibrated against

    intensity = speed / max(1.0, sustainable_speed)
    drain = BASE * (intensity ** INTENSITY_EXPONENT)
    drain *= 1.0 - (resistance / 100.0) * RESISTANCE_FACTOR
    drain *= speed / DRAIN_REFERENCE_SPEED

    if gradient > 0:
        drain *= 1.0 + gradient * GRADIENT_SCALE
    elif gradient < 0:
        drain -= DESCENT_RECOVERY

    return drain
