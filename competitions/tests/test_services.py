from __future__ import annotations

import pytest

from competitions.models import RacePoints
from competitions.services import score_race
from racing.models import Race


def test_best_finisher_scores_for_the_team(race, make_team, make_rider, make_result):
    team = make_team("ALP")
    rider = make_rider("Rider One", team)
    make_result(race, rider, position=1)

    points = score_race(race)

    assert len(points) == 1
    assert points[0].team_id == team.pk
    assert points[0].position == 1
    assert points[0].points == 20


def test_only_the_best_finisher_counts(race, make_team, make_rider, make_result):
    team = make_team("ALP")
    make_result(race, make_rider("Second Placed", team), position=2)
    make_result(race, make_rider("Fourth Placed", team), position=4)

    points = score_race(race)

    assert len(points) == 1
    assert points[0].position == 2
    assert points[0].points == 15


def test_team_with_only_non_finishers_scores_nothing(race, make_team, make_rider, make_result):
    """The D3 test: simulate_race numbers every rider including those who
    never finished, so a team whose only riders abandoned must not score
    off wherever they were numbered."""
    scoring_team = make_team("ALP")
    dnf_team = make_team("DNF")
    make_result(race, make_rider("Winner", scoring_team), position=1)
    make_result(race, make_rider("Abandoned", dnf_team), position=2, finish_time=None)

    points = score_race(race)

    assert {p.team_id for p in points} == {scoring_team.pk}


def test_position_outside_the_points_writes_no_row(race, make_team, make_rider, make_result):
    team = make_team("ALP")
    make_result(race, make_rider("Eleventh", team), position=11)

    points = score_race(race)

    assert points == []
    assert RacePoints.objects.filter(race=race).count() == 0


def test_scoring_twice_is_idempotent(race, make_team, make_rider, make_result):
    team = make_team("ALP")
    make_result(race, make_rider("Rider One", team), position=1)

    first = score_race(race)
    assert RacePoints.objects.filter(race=race).count() == 1

    second = score_race(race)

    # bulk_create(ignore_conflicts=True) never populates pk on the objects
    # it creates in Postgres, so the first call's own return value can't be
    # compared by pk either — what actually matters is that scoring twice
    # does not create a second row.
    assert len(second) == 1
    assert RacePoints.objects.filter(race=race).count() == 1
    assert second[0].team_id == team.pk
    assert second[0].points == first[0].points


def test_unfinished_race_raises(db):
    race = Race.objects.create(
        name="Not Yet Run",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.SCHEDULED,
    )

    with pytest.raises(ValueError):
        score_race(race)
