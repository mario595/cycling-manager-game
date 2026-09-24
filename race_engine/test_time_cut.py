"""Tests for the time-cut (broom wagon) DNF rule.

Once the winner finishes, `RaceState.tick()` fixes a time limit —
`ceil(winner_time * (1 + TIME_CUT_MARGIN))` — and cuts anyone still racing
once time reaches it: DNF, not finished. See `race_engine/README.md`,
*Simulation tick*, and `specs/archive/broom-wagon-time-cut-plan.md`.
"""

from __future__ import annotations

import math
import random

import pytest

from race_engine.formulas import TIME_CUT_MARGIN
from race_engine.models import Course, RaceState, Rider, RiderAttributes, Segment

ATTRS = RiderAttributes(climb=50, sprint=50, flat=50, resistance=50, positioning=60)


@pytest.fixture(autouse=True)
def _isolate_global_random():
    # Every test in this file seeds the global random module (via
    # _make_state) and then keeps drawing from it across its own tick()
    # loop, so the save/restore has to wrap the whole test, not just
    # _make_state — otherwise restoring early would desync the seed from
    # the ticks that follow. This keeps that seeding from leaking into any
    # other, unrelated test's unseeded use of the same stream (matches
    # test_race_logger.py's pattern).
    saved_random_state = random.getstate()
    yield
    random.setstate(saved_random_state)


def _make_state(positions: list[float], distance: float = 10_000.0) -> RaceState:
    random.seed(1)
    riders = [Rider(id=f"r{i}", name=f"R{i}", attributes=ATTRS) for i in range(len(positions))]
    course = Course(segments=[Segment(length=distance, gradient=0.0)])
    state = RaceState.create_initial_state(riders, course, wind=False, seed=1)
    for rs, pos in zip(state.rider_states, positions):
        rs.position = pos
    return state


def test_time_limit_is_unset_until_someone_finishes():
    state = _make_state([0.0, 0.0])
    for _ in range(5):
        state.tick()
    assert state.time_limit is None


def test_time_limit_is_ceil_of_winner_time_times_margin():
    state = _make_state([9_999.0, 0.0])
    while state.rider_states[0].finish_time is None:
        state.tick()
    winner_time = state.rider_states[0].finish_time
    assert state.time_limit == math.ceil(winner_time * (1 + TIME_CUT_MARGIN))


def test_rider_outside_time_limit_is_dnf_and_race_ends_at_the_limit():
    state = _make_state([6_000.0, 0.0])
    while not state.is_finished():
        state.tick()

    a, b = state.rider_states
    assert a.finished and not a.dnf
    assert b.dnf and not b.finished
    assert b.finish_time is None
    assert state.current_time == state.time_limit + 1


def test_rider_inside_time_limit_finishes(monkeypatch):
    monkeypatch.setattr("race_engine.formulas.TIME_CUT_MARGIN", 10.0)
    state = _make_state([6_000.0, 0.0])
    while not state.is_finished():
        state.tick()

    a, b = state.rider_states
    assert a.finished and not a.dnf
    assert b.finished and not b.dnf


def test_rider_crossing_on_the_limit_tick_is_a_finisher(monkeypatch):
    # First, an uncut run to learn A's and B's actual finish ticks at the
    # default margin (large enough that neither rider is cut).
    monkeypatch.setattr("race_engine.formulas.TIME_CUT_MARGIN", 10.0)
    reference = _make_state([6_000.0, 0.0])
    while not reference.is_finished():
        reference.tick()
    a_time = reference.rider_states[0].finish_time
    b_time = reference.rider_states[1].finish_time

    # Pin the margin so the limit lands exactly on B's finish tick:
    # ceil(a_time * (1 + margin)) == ceil(a_time * (b_time / a_time)) ==
    # b_time, since margin is built from that same division. This is only
    # exact because the float round-trip happens to be lossless under this
    # seed — if a future seed change breaks this test, that division is
    # where to look first, not the engine.
    margin = (b_time / a_time) - 1
    monkeypatch.setattr("race_engine.formulas.TIME_CUT_MARGIN", margin)

    state = _make_state([6_000.0, 0.0])
    while not state.is_finished():
        state.tick()

    b = state.rider_states[1]
    assert b.finished and not b.dnf
    assert b.finish_time == state.time_limit


def test_results_list_dnfs_furthest_first():
    state = _make_state([9_999.0, 5_000.0, 2_000.0])
    while not state.is_finished():
        state.tick()

    winner, second, third = state.get_results()
    assert winner.finished and not winner.dnf
    assert second.dnf and third.dnf
    assert second.position > third.position
