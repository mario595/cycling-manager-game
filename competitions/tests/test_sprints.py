from __future__ import annotations

import pytest

from competitions.models import MarkerPoints
from competitions.services import score_sprints
from racing.models import Race, RaceMarker
from riders.models import Rider


def test_top_five_at_a_sprint_score_by_weight(race, make_team, make_rider, make_marker, make_crossing):
    marker = make_marker(race, weight=RaceMarker.Weight.MAJOR)
    team = make_team("ALP")
    rider = make_rider("Winner", team)
    make_crossing(marker, rider, position=1)

    points = score_sprints(race)

    assert len(points) == 1
    assert points[0].team_id == team.pk
    assert points[0].rider_id == rider.pk
    assert points[0].position == 1
    assert points[0].points == 10


def test_team_scores_only_its_best_rider_at_a_marker(race, make_team, make_rider, make_marker, make_crossing):
    marker = make_marker(race)
    team = make_team("ALP")
    first = make_rider("First", team)
    second = make_rider("Second", team)
    make_crossing(marker, first, position=1)
    make_crossing(marker, second, position=2)

    points = score_sprints(race)

    assert len(points) == 1
    assert points[0].rider_id == first.pk
    assert points[0].position == 1
    assert points[0].points == 6


def test_sixth_place_does_not_move_up_when_a_team_doubles(race, make_team, make_rider, make_marker, make_crossing):
    """D3, load-bearing: cutting to the top 5 crossings happens BEFORE
    de-duplicating by team. A team taking 1st and 2nd must not let 6th
    place move up into the scoring places."""
    marker = make_marker(race)
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

    points = score_sprints(race)

    assert {p.team_id for p in points} == {
        doubling_team.pk, third_team.pk, fourth_team.pk, fifth_team.pk,
    }
    assert sixth_team.pk not in {p.team_id for p in points}


def test_mountain_markers_score_nothing(race, make_team, make_rider, make_marker, make_crossing):
    marker = make_marker(race, kind=RaceMarker.Kind.MOUNTAIN)
    team = make_team("ALP")
    make_crossing(marker, make_rider("Climber", team), position=1)

    points = score_sprints(race)

    assert points == []


def test_rider_who_crossed_then_abandoned_keeps_points(race, make_team, make_rider, make_marker, make_crossing, make_result):
    marker = make_marker(race)
    team = make_team("ALP")
    rider = make_rider("Abandoned Later", team)
    make_crossing(marker, rider, position=1)
    make_result(race, rider, position=50, finish_time=None)

    points = score_sprints(race)

    assert len(points) == 1
    assert points[0].rider_id == rider.pk
    assert points[0].points > 0


def test_teamless_rider_is_skipped(race, make_marker, make_crossing):
    marker = make_marker(race)
    rider = Rider.objects.create(
        name="Free Agent", team=None,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    make_crossing(marker, rider, position=1)

    points = score_sprints(race)

    assert points == []


def test_score_sprints_is_idempotent(race, make_team, make_rider, make_marker, make_crossing):
    marker = make_marker(race)
    team = make_team("ALP")
    make_crossing(marker, make_rider("Winner", team), position=1)

    first = score_sprints(race)
    assert MarkerPoints.objects.filter(marker__race=race).count() == 1

    second = score_sprints(race)

    assert len(second) == 1
    assert MarkerPoints.objects.filter(marker__race=race).count() == 1
    assert second[0].team_id == team.pk
    assert second[0].points == first[0].points


def test_score_sprints_rejects_unfinished_race(db):
    race = Race.objects.create(
        name="Not Yet Run",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.SCHEDULED,
    )

    with pytest.raises(ValueError):
        score_sprints(race)


def test_race_without_sprint_markers_scores_nothing(race):
    assert score_sprints(race) == []


def test_points_frozen_when_table_changes(race, make_team, make_rider, make_marker, make_crossing, monkeypatch):
    marker = make_marker(race, weight=RaceMarker.Weight.STANDARD)
    team = make_team("ALP")
    make_crossing(marker, make_rider("Winner", team), position=1)

    points = score_sprints(race)
    awarded = points[0].points

    import competitions.scoring as scoring
    monkeypatch.setitem(scoring.SPRINT_POINTS_BY_WEIGHT["standard"], 1, 999)

    stored = MarkerPoints.objects.get(marker=marker, team=team)
    assert stored.points == awarded
    assert stored.points != 999
