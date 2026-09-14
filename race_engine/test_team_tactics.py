"""Tests for the Tier A team-tactics behaviours (TEAM_TACTICS_PLAN.md).

Covers A2 (role-scaled rotation floor: support riders take more than their
share of front-line time so the leader is protected) and A3 (a pack doesn't
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


def test_support_pulls_more_than_leader():
    """In a tight team pack, the support rider accumulates more pulling
    ticks than the leader over time, since the leader's rotation floor is
    higher (protected) and the support's lower (Tier A2)."""
    riders = [
        _rider("leader", "t1", "leader"),
        _rider("support", "t1", "support"),
    ]
    course = Course(segments=[Segment(length=500_000.0, gradient=0.0)])
    state = RaceState.create_initial_state(riders, course, wind=False)
    # Start tied so who pulls first is decided by the tactics, not a head start.
    for rs in state.rider_states:
        rs.position = 100_000.0

    pulling_ticks = {"leader": 0, "support": 0}
    for _ in range(500):
        state.tick()
        for rs in state.rider_states:
            if rs.pulling:
                pulling_ticks[rs.rider.id] += 1

    assert pulling_ticks["support"] >= pulling_ticks["leader"]


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
