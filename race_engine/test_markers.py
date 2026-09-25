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


def _specialist(rid: str, climb: float = 50.0, sprint: float = 85.0, role: str = "leader") -> Rider:
    return Rider(
        id=rid,
        name=rid,
        attributes=RiderAttributes(
            climb=climb, sprint=sprint, flat=75, resistance=80, positioning=70
        ),
        team_id="t",
        role=role,
    )


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


def test_sprinter_kicks_for_sprint_marker_in_the_early_race():
    """A sprinter inside the window of an early sprint marker starts a
    sprint-sized kick even though the race is far from over (rule 2 is not
    phase-gated)."""
    marker_distance = 40000.0
    course = Course(
        segments=[Segment(length=100000.0, gradient=0.0)],
        markers=[Marker(kind=MarkerKind.SPRINT, distance=marker_distance, name="M")],
    )
    rider = _specialist("s", climb=50, sprint=97)
    state = RaceState.create_initial_state([rider], course, wind=False)
    rs = state.rider_states[0]
    rs.position = marker_distance - 100.0
    assert state.profile.remaining_fraction(rs.position) > 0.25

    state.tick()

    assert rs.surging
    assert rs.sprinting
    assert rs.contested == {0}


def test_non_sprinter_rolls_through_sprint_marker():
    """A rider without the sprint attribute is not a specialist; they ride
    through the marker's window without surging and never decide on it."""
    marker_distance = 40000.0
    course = Course(
        segments=[Segment(length=100000.0, gradient=0.0)],
        markers=[Marker(kind=MarkerKind.SPRINT, distance=marker_distance, name="M")],
    )
    rider = _specialist("rouleur", climb=50, sprint=50)
    state = RaceState.create_initial_state([rider], course, wind=False)
    rs = state.rider_states[0]
    rs.position = marker_distance - 100.0

    for _ in range(10):
        state.tick()
        assert not rs.surging
    assert rs.contested == set()


def test_climber_surges_for_mountain_marker_without_sprinting():
    marker_distance = 40000.0
    course = Course(
        segments=[Segment(length=100000.0, gradient=0.0)],
        markers=[Marker(kind=MarkerKind.MOUNTAIN, distance=marker_distance, name="M")],
    )
    rider = _specialist("c", climb=94, sprint=40)
    state = RaceState.create_initial_state([rider], course, wind=False)
    rs = state.rider_states[0]
    rs.position = marker_distance - 100.0

    state.tick()

    assert rs.surging
    assert not rs.sprinting
    assert rs.contested == {0}


def test_leader_contests_too():
    """The bridge rule is support-only; the marker rule is role-blind — a
    leader who is a specialist in the window contests."""
    marker_distance = 40000.0
    course = Course(
        segments=[Segment(length=100000.0, gradient=0.0)],
        markers=[Marker(kind=MarkerKind.SPRINT, distance=marker_distance, name="M")],
    )
    rider = _specialist("leader", climb=40, sprint=98, role="leader")
    state = RaceState.create_initial_state([rider], course, wind=False)
    rs = state.rider_states[0]
    rs.position = marker_distance - 100.0

    state.tick()

    assert rs.rider.role == "leader"
    assert rs.surging
    assert rs.sprinting


def test_low_energy_specialist_rolls_through_and_does_not_retry():
    """Decided on the moment the window is entered, whatever the energy gate
    says — a rider below MARKER_MIN_ENERGY rolls through and never re-tries
    as energy trickles back."""
    from race_engine.formulas import MARKER_MIN_ENERGY

    marker_distance = 40000.0
    course = Course(
        segments=[Segment(length=100000.0, gradient=0.0)],
        markers=[Marker(kind=MarkerKind.SPRINT, distance=marker_distance, name="M")],
    )
    rider = _specialist("tired", climb=50, sprint=97)
    state = RaceState.create_initial_state([rider], course, wind=False)
    rs = state.rider_states[0]
    rs.position = marker_distance - 100.0
    rs.energy = MARKER_MIN_ENERGY - 5.0

    state.tick()
    assert 0 in rs.contested
    assert not rs.surging

    for _ in range(10):
        state.tick()
        assert not rs.surging
    assert rs.contested == {0}


def test_marker_is_contested_once():
    """A rider who has already decided on a marker does not re-contest it,
    even if they are still inside its window when the surge ends."""
    marker_distance = 40000.0
    course = Course(
        segments=[Segment(length=100000.0, gradient=0.0)],
        markers=[Marker(kind=MarkerKind.SPRINT, distance=marker_distance, name="M")],
    )
    rider = _specialist("s", climb=50, sprint=97)
    state = RaceState.create_initial_state([rider], course, wind=False)
    rs = state.rider_states[0]
    rs.position = marker_distance - 100.0

    state.tick()
    assert rs.surging
    assert rs.contested == {0}

    # The surge is over and the rider is placed back inside the window — the
    # decision has been made, so there is no second effort.
    rs.surge_ticks = 0
    rs.surge_cooldown = 0
    rs.position = marker_distance - 100.0

    state.tick()

    assert not rs.surging
    assert rs.contested == {0}


def test_finish_line_marker_is_left_to_the_finish_sprint():
    """A marker exactly on the finish line is excluded from the contest rule —
    rule 1 (the finish sprint in the last kilometer) owns the line."""
    from race_engine.formulas import SPRINT_DISTANCE

    course = Course(
        segments=[Segment(length=20000.0, gradient=0.0)],
        markers=[Marker(kind=MarkerKind.MOUNTAIN, distance=20000.0, name="M")],
    )
    rider = _specialist("s", climb=50, sprint=95)
    state = RaceState.create_initial_state([rider], course, wind=False)
    rs = state.rider_states[0]
    rs.position = 17000.0

    surged_outside_final_km = False
    surged_in_final_km = False
    for _ in range(3000):
        state.tick()
        if rs.surging and rs.position < state.profile.total_distance - SPRINT_DISTANCE:
            surged_outside_final_km = True
        if rs.surging and rs.position >= state.profile.total_distance - SPRINT_DISTANCE:
            surged_in_final_km = True
        if rs.finished:
            break

    assert rs.finished
    assert not surged_outside_final_km
    assert surged_in_final_km