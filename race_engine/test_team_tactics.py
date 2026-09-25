"""Tests for the Tier A team-tactics behaviours (TEAM_TACTICS_PLAN.md).

Covers A2 (role-scaled rotation floor: the leader is credited with a deeper
rotation average than an equal support teammate, protecting them from the
drop test and fatigue when they ride at the front) and A3 (a pack doesn't
chase a break made up solely of its own teammates).
"""

from __future__ import annotations

import pytest

from race_engine.formulas import BREAK_CLEAR_DISTANCE
from race_engine.models import (
    Course,
    RaceSetupError,
    RaceState,
    Rider,
    RiderAttributes,
    Segment,
    run_race,
)

ATTRS = RiderAttributes(climb=50, sprint=50, flat=50, resistance=50, positioning=60)


def _rider(rid: str, team: str, role: str) -> Rider:
    return Rider(id=rid, name=rid, attributes=ATTRS, team_id=team, role=role)


def test_rotation_floor_protects_leader_at_the_front():
    """A2's rotation floor is a fatigue-protection *credit*, not a pack-geometry
    rule: a team's leader is credited with a deeper rotation average than an
    equal support teammate, so the drop-test and fatigue reference rate a
    leader at the front as more sheltered. Deterministic — no RNG.

    Pack size matters. The floor is `share * (pack_size - 1)`, and
    `draft_hold_multiplier` treats any depth below 1.0 as fully exposed
    (`DRAFT_HOLD_MIN`), so a 2-rider pack never binds: both the 0.65 leader
    credit and the 0.35 support credit sit under the 1.0 exposure threshold
    and the two ride identically. The floor clears it only with three or more
    riders, which is what this test pins. (The original version tallied the
    positional `pulling` flag in a 2-rider pack — the flag is set for
    whichever rider is physically at the front, and the A2 credit does not
    feed it — so it flipped with the speed jitter.)"""
    from race_engine.formulas import (
        DRAFT_HOLD_MIN,
        ROTATION_SHARE_LEADER,
        ROTATION_SHARE_SUPPORT,
        draft_hold_multiplier,
    )

    positioning = 60
    pack_size = 3

    # The credit the drop-test and fatigue reference see (mirrored from
    # `models.py` tick(), "Role-scaled (Tier A2)"). At the front (depth 0,
    # gap_factor 1, no teammate on a wheel ahead) the rotation floor
    # `share * (pack_size - 1)` is the binding term.
    leader_front = ROTATION_SHARE_LEADER * (pack_size - 1)
    support_front = ROTATION_SHARE_SUPPORT * (pack_size - 1)

    assert ROTATION_SHARE_LEADER > ROTATION_SHARE_SUPPORT
    # The floor binds from three riders up (a 2-rider pack stays below the
    # exposure threshold on both sides and the pair would ride identically).
    assert leader_front > 1.0
    # The support at the front gets no credit (fully exposed); the leader
    # gets partial shelter — the leader is the protected one.
    assert draft_hold_multiplier(positioning, support_front, 0.0) == DRAFT_HOLD_MIN
    assert (
        draft_hold_multiplier(positioning, leader_front, 0.0)
        > draft_hold_multiplier(positioning, support_front, 0.0)
    )
    # The floor protects but never over-credits: a leader at the front is
    # still rated more exposed than a rider tucked into the wheels.
    assert draft_hold_multiplier(positioning, leader_front, 0.0) < (
        draft_hold_multiplier(positioning, 2.0, 0.0)
    )


def test_pack_does_not_chase_teammates_only_break():
    """A pack whose only rider up the road is a teammate of every chaser
    should not ride at the full chase tempo (Tier A3) — riding it down
    would just bring back their own break."""
    from race_engine.formulas import (
        Terrain,
        pack_tempo_fraction,
    )

    # willingness 0.0 (nobody sees a chaseable break, e.g. all pack members
    # share a team with the rider up the road) must equal the no-break tempo.
    no_break = pack_tempo_fraction(0.5, Terrain.FLAT, 0.0, 0.0)
    full_chase = pack_tempo_fraction(0.5, Terrain.FLAT, 1.0, 0.0)
    assert no_break < full_chase


def test_mixed_team_pack_break_ahead_reduces_chase_below_full():
    """A pack that is only partly willing to chase (some members' own
    teammate is the one up the road) rides slower than a pack that's fully
    willing, but still faster than one with nobody up the road at all."""
    from race_engine.formulas import Terrain, pack_tempo_fraction

    none = pack_tempo_fraction(0.5, Terrain.FLAT, 0.0, 0.0)
    half = pack_tempo_fraction(0.5, Terrain.FLAT, 0.5, 0.0)
    full = pack_tempo_fraction(0.5, Terrain.FLAT, 1.0, 0.0)
    assert none < half < full


def _pack_speed_with_break_ahead(chaser_team: str, breaker_team: str) -> float:
    """Build a 4-rider chase pack plus one rider clear ahead, tick once, and
    return the chase pack's common effective speed."""
    riders = [_rider(f"c{i}", chaser_team, "support") for i in range(4)]
    riders[0].role = "leader"
    breaker = _rider("breaker", breaker_team, "leader")
    course = Course(segments=[Segment(length=500_000.0, gradient=0.0)])
    state = RaceState.create_initial_state(riders + [breaker], course, wind=False)

    state.rider_states[-1].position = 100_000.0 + BREAK_CLEAR_DISTANCE + 20.0
    for rs in state.rider_states[:-1]:
        rs.position = 100_000.0

    state.tick()
    return state.rider_states[0].speed


def test_break_of_teammates_only_does_not_trigger_full_chase_in_tick():
    """End-to-end: a pack chasing its own teammate's break rides slower than
    an identical pack chasing a genuine rival break (Tier A3) — riding the
    full chase tempo to catch your own rider helps nobody."""
    teammate_break_speed = _pack_speed_with_break_ahead("t1", "t1")
    rival_break_speed = _pack_speed_with_break_ahead("t1", "t2")

    assert teammate_break_speed < rival_break_speed


def test_run_race_rejects_a_team_with_two_leaders():
    """load_config has always enforced this; run_race must too, since the
    Django path (racing/adapters.py) builds Rider dataclasses directly and
    never goes through load_config — see racing/README.md, *Squads*."""
    riders = [
        _rider("c1", "t1", "leader"),
        _rider("c2", "t1", "leader"),
    ]
    course = Course(segments=[Segment(length=1000.0, gradient=0.0)])

    with pytest.raises(RaceSetupError, match="2 leaders"):
        run_race(riders, course)


def test_run_race_rejects_a_team_with_no_leader():
    riders = [
        _rider("c1", "t1", "support"),
        _rider("c2", "t1", "support"),
    ]
    course = Course(segments=[Segment(length=1000.0, gradient=0.0)])

    with pytest.raises(RaceSetupError, match="no leader"):
        run_race(riders, course)
