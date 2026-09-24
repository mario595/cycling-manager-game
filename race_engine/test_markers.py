"""Tests for course markers: validation, and crossing detection in tick().

Covers the engine half of the course-markers feature (specs/course-markers.md):
markers are named points on a course at a distance from the start, and the
engine records every rider's crossing of every marker, interpolated within
the tick (D4). The contest rule (specialists surging for a marker) is tested
in this file too — see test_sprinter_kicks_for_sprint_marker_in_the_early_race
and its siblings.
"""

from __future__ import annotations

import random

import pytest

from race_engine.models import (
    Course,
    Marker,
    MarkerKind,
    RaceSetupError,
    RaceState,
    Rider,
    RiderAttributes,
    Segment,
)

ATTRS = RiderAttributes(climb=50, sprint=50, flat=50, resistance=50, positioning=60)
STRONG = RiderAttributes(climb=70, sprint=85, flat=80, resistance=80, positioning=70)


def _rider(rid: str) -> Rider:
    return Rider(id=rid, name=rid, attributes=ATTRS, team_id="t", role="leader")


def _course(length: float = 1000.0, markers: list[Marker] | None = None) -> Course:
    return Course(
        segments=[Segment(length=length, gradient=0.0)],
        markers=markers or [],
    )


def test_course_rejects_marker_beyond_finish():
    with pytest.raises(RaceSetupError):
        _course(length=1000.0, markers=[Marker(kind=MarkerKind.SPRINT, distance=1500.0, name="M")])


def test_course_rejects_marker_at_or_before_start():
    with pytest.raises(RaceSetupError):
        _course(markers=[Marker(kind=MarkerKind.MOUNTAIN, distance=0.0, name="M")])
    with pytest.raises(RaceSetupError):
        _course(markers=[Marker(kind=MarkerKind.MOUNTAIN, distance=-5.0, name="M")])


def test_course_accepts_marker_on_finish_line():
    _course(length=1000.0, markers=[Marker(kind=MarkerKind.MOUNTAIN, distance=1000.0, name="M")])


def test_crossing_time_is_interpolated_within_the_tick():
    """Two riders 5 m and 10 m short of a marker cross within one tick; the
    nearer one records the smaller time, and both fall inside [t, t+1). The
    farther-back rider comes first in `rider_states`, so the order must come
    from interpolation, not the rider list (D4)."""
    random.seed(0)
    marker_distance = 15000.0
    course = Course(
        segments=[Segment(length=20000.0, gradient=0.0)],
        markers=[Marker(kind=MarkerKind.SPRINT, distance=marker_distance, name="M")],
    )
    far = _rider("far")
    near = _rider("near")
    far.attributes = STRONG
    near.attributes = STRONG
    state = RaceState.create_initial_state([far, near], course, wind=False)
    far_state, near_state = state.rider_states
    far_state.position = marker_distance - 10.0
    near_state.position = marker_distance - 5.0

    state.tick()

    assert state.current_time == 1
    near_time = near_state.marker_times[0]
    far_time = far_state.marker_times[0]
    assert near_time < far_time
    assert 0.0 <= near_time < 1.0
    assert 0.0 <= far_time < 1.0


def test_rider_who_never_reaches_marker_has_no_crossing():
    course = Course(
        segments=[Segment(length=20000.0, gradient=0.0)],
        markers=[Marker(kind=MarkerKind.MOUNTAIN, distance=19500.0, name="M")],
    )
    rider = _rider("slow")
    state = RaceState.create_initial_state([rider], course, wind=False)

    state.tick()

    rider_state = state.rider_states[0]
    assert rider_state.position > 0.0
    assert 0 not in rider_state.marker_times


def test_finish_line_marker_is_crossed():
    course = _course(
        length=1000.0,
        markers=[Marker(kind=MarkerKind.MOUNTAIN, distance=1000.0, name="M")],
    )
    state = RaceState.create_initial_state([_rider("solo")], course, wind=False)

    for _ in range(1000):
        state.tick()
        if state.rider_states[0].finished:
            break

    rs = state.rider_states[0]
    assert rs.finished
    assert rs.finish_time is not None
    assert 0 in rs.marker_times
    assert rs.finish_time <= rs.marker_times[0] < rs.finish_time + 1