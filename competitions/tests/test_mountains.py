from __future__ import annotations

import pytest

from competitions.models import MarkerPoints
from competitions.services import score_mountains
from racing.models import Race, RaceMarker
from riders.models import Rider


def test_top_five_at_a_climb_score_by_category(race, make_team, make_rider, make_marker, make_crossing):
    marker = make_marker(race, kind=RaceMarker.Kind.MOUNTAIN,
                         category=RaceMarker.Category.HC)
    team = make_team("ALP")
    winner = make_rider("Winner", team)
    make_crossing(marker, winner, position=1)
    other = make_team("BET")
    make_crossing(marker, make_rider("Second", other), position=2)

    points = score_mountains(race)

    assert len(points) == 2
    assert points[0].team_id == team.pk
    assert points[0].rider_id == winner.pk
    assert points[0].position == 1
    assert points[0].points == 10
    assert points[1].points == 7


def test_team_scores_only_its_best_rider_at_a_climb(race, make_team, make_rider, make_marker, make_crossing):
    marker = make_marker(race, kind=RaceMarker.Kind.MOUNTAIN)
    team = make_team("ALP")
    first = make_rider("First", team)
    second = make_rider("Second", team)
    make_crossing(marker, first, position=1)
    make_crossing(marker, second, position=2)

    points = score_mountains(race)

    assert len(points) == 1
    assert points[0].rider_id == first.pk
    assert points[0].position == 1
    assert points[0].points == 6


def test_sixth_place_does_not_move_up_when_a_team_doubles_on_a_climb(
    race, make_team, make_rider, make_marker, make_crossing,
):
    """Cut to the top 5 crossings happens BEFORE de-duplicating by team."""
    marker = make_marker(race, kind=RaceMarker.Kind.MOUNTAIN)
    doubling_team = make_team("ALP")
    make_crossing(marker, make_rider("First", doubling_team), position=1)
    make_crossing(marker, make_rider("Second", doubling_team), position=2)
    third_team = make_team("BET")
    make_crossing(marker, make_rider("Third", third_team), position=3)
    fourth_team = make_team("GAM")
    make_crossing(marker, make_rider("Fourth", fourth_team), position=4)
    fifth_team = make_team("DEL")
    make_crossing(marker, make_rider("Fifth", fifth_team), position=5)
    sixth_team = make_team("EPS")
    make_crossing(marker, make_rider("Sixth", sixth_team), position=6)

    points = score_mountains(race)

    assert {p.team_id for p in points} == {
        doubling_team.pk, third_team.pk, fourth_team.pk, fifth_team.pk,
    }
    assert sixth_team.pk not in {p.team_id for p in points}


def test_sprint_markers_score_nothing_as_mountains(race, make_team, make_rider, make_marker, make_crossing):
    marker = make_marker(race, kind=RaceMarker.Kind.SPRINT)
    team = make_team("ALP")
    make_crossing(marker, make_rider("Sprinter", team), position=1)

    points = score_mountains(race)

    assert points == []


def test_summit_finish_scores_like_any_climb(
    race, make_team, make_rider, make_marker, make_crossing,
):
    """A mountain marker on the finish line is not a special case: the same
    table, the same single award, nothing doubled."""
    summit = make_marker(
        race, kind=RaceMarker.Kind.MOUNTAIN, name="Final Top", distance=40000.0,
        category=RaceMarker.Category.HC,
    )
    mid_climb = make_marker(
        race, kind=RaceMarker.Kind.MOUNTAIN, name="First Climb", distance=20000.0,
        category=RaceMarker.Category.CAT1,
    )
    team = make_team("ALP")
    make_crossing(summit, make_rider("Winner", team), position=1)
    make_crossing(mid_climb, make_rider("Same Rider", team), position=1)

    points = score_mountains(race)

    by_name = {p.marker.name: p.points for p in points}
    assert by_name == {"Final Top": 10, "First Climb": 8}


def test_rider_who_crossed_a_climb_then_abandoned_keeps_points(
    race, make_team, make_rider, make_marker, make_crossing, make_result,
):
    marker = make_marker(race, kind=RaceMarker.Kind.MOUNTAIN)
    team = make_team("ALP")
    rider = make_rider("Abandoned Later", team)
    make_crossing(marker, rider, position=1)
    make_result(race, rider, position=50, finish_time=None)

    points = score_mountains(race)

    assert len(points) == 1
    assert points[0].rider_id == rider.pk
    assert points[0].points > 0


def test_teamless_rider_is_skipped(race, make_marker, make_crossing):
    marker = make_marker(race, kind=RaceMarker.Kind.MOUNTAIN)
    rider = Rider.objects.create(
        name="Free Agent", team=None,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    make_crossing(marker, rider, position=1)

    points = score_mountains(race)

    assert points == []


def test_score_mountains_is_idempotent(race, make_team, make_rider, make_marker, make_crossing):
    marker = make_marker(race, kind=RaceMarker.Kind.MOUNTAIN)
    team = make_team("ALP")
    make_crossing(marker, make_rider("Winner", team), position=1)

    first = score_mountains(race)
    assert MarkerPoints.objects.filter(marker__race=race).count() == 1

    second = score_mountains(race)

    assert len(second) == 1
    assert MarkerPoints.objects.filter(marker__race=race).count() == 1
    assert second[0].team_id == team.pk
    assert second[0].points == first[0].points


def test_score_mountains_rejects_unfinished_race(db):
    race = Race.objects.create(
        name="Not Yet Run",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.SCHEDULED,
    )

    with pytest.raises(ValueError):
        score_mountains(race)


def test_mountain_points_frozen_when_table_changes(
    race, make_team, make_rider, make_marker, make_crossing, monkeypatch,
):
    marker = make_marker(race, kind=RaceMarker.Kind.MOUNTAIN)
    team = make_team("ALP")
    make_crossing(marker, make_rider("Winner", team), position=1)

    points = score_mountains(race)
    awarded = points[0].points

    import competitions.scoring as scoring
    monkeypatch.setitem(scoring.MOUNTAIN_POINTS_BY_CATEGORY["cat2"], 1, 999)

    stored = MarkerPoints.objects.get(marker=marker, team=team)
    assert stored.points == awarded
    assert stored.points != 999
