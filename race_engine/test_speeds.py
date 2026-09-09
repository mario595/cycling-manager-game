"""Tests for the resistance-model terrain speed and the chase/bridge reflex.

The audit harness (`race_engine/audit.py`) answers "did the race come out
right"; these answer "is the model right" and fail fast. See
`FINDING1_PLAN.md` section 3c for the source of the assertions below.
"""

from __future__ import annotations

from race_engine.formulas import (
    BRIDGE_MAX_DEPTH,
    compute_base_speed,
)
from race_engine.models import Course, RaceState, Rider, RiderAttributes, Segment

# Shared roster used throughout DOMAIN.md / ENGINE_FINDINGS.md, one rider per
# archetype (attribute values from ENGINE_FINDINGS.md's shared roster).
GC1 = RiderAttributes(climb=94, sprint=30, flat=40, resistance=80, positioning=52)
PU1 = RiderAttributes(climb=76, sprint=85, flat=60, resistance=68, positioning=72)
RU1 = RiderAttributes(climb=60, sprint=60, flat=80, resistance=86, positioning=62)
SP1 = RiderAttributes(climb=30, sprint=97, flat=82, resistance=62, positioning=88)

ARCHETYPES = {"gc1": GC1, "pu1": PU1, "ru1": RU1, "sp1": SP1}


# -- Continuity -----------------------------------------------------------
# The bug this guards against (FINDING1_PLAN.md sec 1a): the old model
# switched from a flat lerp table to a disjoint climb lerp table the instant
# gradient > 0, producing a true jump discontinuity (a 106% speed swing on a
# 2.5% drag). The new resistance model has no branch at gradient 0, so a tiny
# gradient step should only ever produce a proportionally tiny speed change.
# 0.15 m/s is generous around a 0.05% gradient step given the steepest slope
# in the roster (sp1, ~1.9 m/s per gradient %) — small next to the old
# model's multi-m/s jump, but not so tight it flags the model's real slope.
def test_continuity_at_gradient_zero():
    for name, attrs in ARCHETYPES.items():
        v0 = compute_base_speed(attrs, 0.0)
        v_small = compute_base_speed(attrs, 0.05)
        assert abs(v0 - v_small) < 0.15, f"{name}: jump at gradient 0 ({v0} vs {v_small})"


# -- Monotonicity -----------------------------------------------------------
def test_monotone_decreasing_in_gradient():
    for name, attrs in ARCHETYPES.items():
        gradients = [g / 10 for g in range(-80, 151, 5)]  # -8% .. 15%
        speeds = [compute_base_speed(attrs, g) for g in gradients]
        for i in range(len(speeds) - 1):
            assert speeds[i] >= speeds[i + 1] - 1e-9, (
                f"{name}: speed increased from {gradients[i]}% to {gradients[i+1]}%"
            )


# -- Calibration table --------------------------------------------------
# Real-world speed bands (km/h) this model should land inside. Doubles as
# executable documentation — this is the table to edit when re-tuning.
CALIBRATION_BANDS_KMH = {
    0.0: {"gc1": (43, 50), "pu1": (44, 51), "ru1": (46, 53), "sp1": (46, 53)},
    2.5: {"gc1": (33, 40), "pu1": (32, 40), "ru1": (32, 39), "sp1": (29, 37)},
    5.0: {"gc1": (25, 32), "pu1": (24, 31), "ru1": (22, 29), "sp1": (19, 26)},
    8.0: {"gc1": (18, 25), "pu1": (16, 23), "ru1": (15, 21), "sp1": (12, 19)},
    12.0: {"gc1": (12, 19), "pu1": (11, 17), "ru1": (9, 16), "sp1": (7, 14)},
    -5.0: {"gc1": (60, 71), "pu1": (65, 76), "ru1": (65, 76), "sp1": (68, 79)},
}


def test_calibration_table():
    for gradient, bands in CALIBRATION_BANDS_KMH.items():
        for name, (lo, hi) in bands.items():
            kmh = compute_base_speed(ARCHETYPES[name], gradient) * 3.6
            assert lo <= kmh <= hi, f"{name} at {gradient}%: {kmh:.1f} km/h outside [{lo}, {hi}]"


# -- Spread bands -------------------------------------------------------
# Fastest/slowest ratio across the roster at a gradient — the number that
# must look like real racing (real cycling: ~10% spread on the flat, ~30% on
# a 5% climb, ~45% on 8%).
def _spread(gradient: float) -> float:
    speeds = [compute_base_speed(a, gradient) for a in ARCHETYPES.values()]
    return max(speeds) / min(speeds)


def test_spread_bands():
    assert 1.05 <= _spread(0.0) <= 1.12
    assert 1.25 <= _spread(5.0) <= 1.40
    assert 1.35 <= _spread(8.0) <= 1.55


# -- Reflex tests ---------------------------------------------------------
def _make_state(n: int, positions: list[float]) -> RaceState:
    riders = [
        Rider(id=f"r{i}", name=f"R{i}", attributes=RU1) for i in range(n)
    ]
    # A long course with all positions placed well before the finish, so the
    # finish-sprint rule (rule 1, SPRINT_DISTANCE from the line) never fires
    # and only the bridge/chase rule (rule 3) is under test. Positions are in
    # the transition/finale phase (< ATTACK_PHASE_THRESHOLD remaining) so the
    # bridge rule's phase gate is active.
    course = Course(segments=[Segment(length=1_000_000.0, gradient=0.0)])
    state = RaceState.create_initial_state(riders, course)
    for rs, pos in zip(state.rider_states, positions):
        rs.position = pos
        rs.energy = 100.0
    return state


def test_no_break_no_surges():
    """A compact bunch with no break produces zero surges."""
    state = _make_state(6, [899_000, 898_980, 898_960, 898_940, 898_920, 898_900])
    state.tick()
    assert not any(rs.surging for rs in state.rider_states)


def test_clear_break_surges_only_at_front_depths():
    """One rider clear (> BREAK_CLEAR_DISTANCE) triggers surges only from
    riders within BRIDGE_MAX_DEPTH of their own group's front."""
    # r0 is 100m clear of a tight r1..r6 chain (each 10m apart).
    positions = [899_100.0] + [899_000.0 - 10 * i for i in range(6)]
    state = _make_state(7, positions)
    state.tick()
    for i, rs in enumerate(state.rider_states):
        if i == 0:
            continue  # the break itself, not a chaser
        depth = i - 1  # r1 is depth 0, r2 depth 1, ... within the chasing group
        if rs.surging:
            assert depth <= BRIDGE_MAX_DEPTH, (
                f"r{i} at depth {depth} surged — should only bridge from the front"
            )


def test_far_break_no_surge():
    """A rider 400m clear is out of bridging range (BRIDGE_GAP_MAX = 150m)."""
    positions = [899_400.0, 899_000.0, 898_990.0, 898_980.0]
    state = _make_state(4, positions)
    state.tick()
    assert not any(rs.surging for i, rs in enumerate(state.rider_states) if i != 0)
