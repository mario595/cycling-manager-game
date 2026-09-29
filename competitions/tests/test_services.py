from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone

import pytest

from competitions.models import MarkerPoints, RacePoints
from competitions.services import points_by_team, score_race, score_sprints
from racing.models import Race, RaceMarker
from schedule.models import SEASON_WEEKS, Season, Week


def make_season_with_weeks() -> Season:
    """A season with all twelve weeks, matching the pattern in
    competitions/tests/test_standings.py's make_season."""
    starts_at = datetime(2027, 1, 4, tzinfo=dt_timezone.utc)  # a Monday
    season = Season.objects.create(number=1, starts_at=starts_at)
    for week_number in range(1, SEASON_WEEKS + 1):
        week_start = season.starts_at + timedelta(weeks=week_number - 1)
        Week.objects.create(
            season=season, number=week_number,
            starts_at=week_start, ends_at=week_start + timedelta(weeks=1),
        )
    return season


def make_race_in_week(season: Season, week_number: int, name: str, day_offset: int = 0) -> Race:
    week = season.weeks.get(number=week_number)
    return Race.objects.create(
        name=name,
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.FINISHED,
        week=week,
        starts_at=week.starts_at + timedelta(days=day_offset),
    )


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


def test_points_by_team_sums_a_weeks_races(db, make_team, make_rider, make_result):
    season = make_season_with_weeks()
    team = make_team("ALP")
    week = season.weeks.get(number=1)

    race1 = make_race_in_week(season, 1, "Race One")
    make_result(race1, make_rider("Rider One", team), position=1)
    score_race(race1)

    race2 = make_race_in_week(season, 1, "Race Two", day_offset=1)
    make_result(race2, make_rider("Rider Two", team), position=3)
    score_race(race2)

    assert points_by_team(week) == {team.pk: 20 + 12}


def test_points_by_team_omits_teams_that_scored_nothing(db, make_team, make_rider, make_result):
    season = make_season_with_weeks()
    scorer = make_team("ALP")
    also_scorer = make_team("BET")
    silent = make_team("SIL")  # entered nobody, or never finished in points
    week = season.weeks.get(number=1)

    race = make_race_in_week(season, 1, "Race One")
    make_result(race, make_rider("Winner", scorer), position=1)
    make_result(race, make_rider("Third", also_scorer), position=3)
    score_race(race)

    assert points_by_team(week) == {scorer.pk: 20, also_scorer.pk: 12}
    assert silent.pk not in points_by_team(week)


def test_points_by_team_adds_sprint_points(db, make_team, make_rider, make_result, make_marker, make_crossing):
    season = make_season_with_weeks()
    team = make_team("ALP")
    week = season.weeks.get(number=1)

    race = make_race_in_week(season, 1, "Race One")
    make_result(race, make_rider("Finisher", team), position=3)
    score_race(race)

    marker = make_marker(race, weight=RaceMarker.Weight.STANDARD)
    make_crossing(marker, make_rider("Sprinter", team), position=1)
    score_sprints(race)

    assert points_by_team(week) == {team.pk: 12 + 6}


def test_points_by_team_ignores_mountain_marker_points(db, make_team, make_rider, make_marker):
    season = make_season_with_weeks()
    team = make_team("ALP")
    week = season.weeks.get(number=1)
    race = make_race_in_week(season, 1, "Race One")
    mountain_marker = make_marker(race, kind=RaceMarker.Kind.MOUNTAIN)
    rider = make_rider("Climber", team)

    # A hand-made MarkerPoints row on a mountain marker, as #17 will
    # eventually write — must never leak into the sprint total here.
    MarkerPoints.objects.create(
        marker=mountain_marker, team=team, rider=rider, position=1, points=999,
    )

    assert points_by_team(week) == {}
