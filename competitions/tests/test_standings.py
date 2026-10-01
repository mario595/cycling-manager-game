from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone

from competitions.services import (
    score_general_classification,
    score_mountains,
    score_race,
    score_sprints,
    standings,
)
from racing.models import Race, RaceMarker, RaceResult, StageRace
from schedule.models import SEASON_WEEKS, Season, Week


def make_season(number: int = 1, starts_at: datetime | None = None) -> Season:
    """A season with all twelve weeks, matching the pattern in
    schedule/tests/test_services.py's make_season_with_weeks — plain
    Season.objects.create() does not create Week rows; only load_season
    does that in real use."""
    starts_at = starts_at or datetime(2027, 1, 4, tzinfo=dt_timezone.utc)  # a Monday
    season = Season.objects.create(number=number, starts_at=starts_at)
    for week_number in range(1, SEASON_WEEKS + 1):
        week_start = season.starts_at + timedelta(weeks=week_number - 1)
        Week.objects.create(
            season=season, number=week_number,
            starts_at=week_start, ends_at=week_start + timedelta(weeks=1),
        )
    return season


def make_race_in_week(season: Season, week_number: int, name: str) -> Race:
    week = season.weeks.get(number=week_number)
    return Race.objects.create(
        name=name,
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.FINISHED,
        week=week,
        starts_at=week.starts_at,
    )


def test_totals_accumulate_across_races(db, make_team, make_rider, make_result):
    season = make_season()
    team = make_team("ALP")

    race1 = make_race_in_week(season, 1, "Race One")
    make_result(race1, make_rider("Rider One", team), position=1)
    score_race(race1)

    race2 = make_race_in_week(season, 2, "Race Two")
    make_result(race2, make_rider("Rider Two", team), position=3)
    score_race(race2)

    table = standings(season)

    assert len(table) == 1
    assert table[0]["team"].pk == team.pk
    assert table[0]["points"] == 20 + 12


def test_team_with_no_points_appears_on_zero(db, make_team, make_rider, make_result):
    season = make_season()
    scorer = make_team("ALP")
    zero_team = make_team("ZER")  # entered nothing, or never scored

    race = make_race_in_week(season, 1, "Race One")
    make_result(race, make_rider("Rider One", scorer), position=1)
    score_race(race)

    table = standings(season)
    by_team = {e["team"].pk: e for e in table}

    assert zero_team.pk not in by_team  # no RacePoints row exists at all
    assert by_team[scorer.pk]["points"] == 20


def test_countback_breaks_a_tie_on_points(db, make_team, make_rider, make_result):
    """Two teams level on total points (20 each), reached by different
    position mixes: winner_team has a single win (20); runner_up_team has
    a 3rd and a 5th (12 + 8 = 20) and no win at all. Countback must rank
    winner_team first on wins even though the totals match exactly."""
    season = make_season()
    winner_team = make_team("WIN")
    runner_up_team = make_team("RUP")

    race1 = make_race_in_week(season, 1, "Race One")
    make_result(race1, make_rider("W1", winner_team), position=1)
    score_race(race1)

    race2 = make_race_in_week(season, 2, "Race Two")
    make_result(race2, make_rider("R1", runner_up_team), position=3)
    score_race(race2)

    race3 = make_race_in_week(season, 3, "Race Three")
    make_result(race3, make_rider("R2", runner_up_team), position=5)
    score_race(race3)

    table = standings(season)
    by_team = {e["team"].pk: e for e in table}

    assert by_team[winner_team.pk]["points"] == 20
    assert by_team[runner_up_team.pk]["points"] == 20
    assert table[0]["team"].pk == winner_team.pk


def test_races_outside_a_season_are_excluded(db, make_team, make_rider, make_result):
    season = make_season()
    team = make_team("ALP")

    in_season_race = make_race_in_week(season, 1, "In Season")
    make_result(in_season_race, make_rider("Rider One", team), position=1)
    score_race(in_season_race)

    ad_hoc_race = Race.objects.create(
        name="Ad Hoc", course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.FINISHED,
    )
    make_result(ad_hoc_race, make_rider("Rider Two", team), position=1)
    score_race(ad_hoc_race)

    table = standings(season)

    assert table[0]["points"] == 20  # only the in-season race counted


def test_standings_include_sprint_points_in_total(db, make_team, make_rider, make_result, make_marker, make_crossing):
    season = make_season()
    team = make_team("ALP")

    race = make_race_in_week(season, 1, "Race One")
    make_result(race, make_rider("Finisher", team), position=3)
    score_race(race)

    marker = make_marker(race, weight=RaceMarker.Weight.STANDARD)
    sprinter = make_rider("Sprinter", team)
    make_crossing(marker, sprinter, position=1)
    score_sprints(race)

    table = standings(season)

    assert table[0]["points"] == 12 + 6
    assert table[0]["sprint_points"] == 6


def test_team_with_only_sprint_points_appears_in_standings(db, make_team, make_rider, make_marker, make_crossing):
    season = make_season()
    team = make_team("ALP")

    race = make_race_in_week(season, 1, "Race One")
    marker = make_marker(race)
    make_crossing(marker, make_rider("Sprinter", team), position=1)
    score_sprints(race)

    table = standings(season)
    by_team = {e["team"].pk: e for e in table}

    assert by_team[team.pk]["points"] == 6
    assert by_team[team.pk]["sprint_points"] == 6
    assert by_team[team.pk]["positions"] == {}


def test_sprint_points_do_not_count_in_countback(db, make_team, make_rider, make_result, make_marker, make_crossing):
    """A finish 1st (20 points) and a sprint-only team that racked up the
    same total via sprint wins must not tie on countback — sprint wins are
    not '1st places' for tie-breaking."""
    season = make_season()
    finisher_team = make_team("FIN")
    sprinter_team = make_team("SPR")

    race1 = make_race_in_week(season, 1, "Race One")
    make_result(race1, make_rider("Winner", finisher_team), position=1)
    score_race(race1)

    race2 = make_race_in_week(season, 2, "Race Two")
    marker1 = make_marker(race2, name="Sprint A", weight=RaceMarker.Weight.MAJOR)
    make_crossing(marker1, make_rider("Sprinter A", sprinter_team), position=1)
    race3 = make_race_in_week(season, 3, "Race Three")
    marker2 = make_marker(race3, name="Sprint B", weight=RaceMarker.Weight.MAJOR)
    make_crossing(marker2, make_rider("Sprinter B", sprinter_team), position=1)
    score_sprints(race2)
    score_sprints(race3)

    table = standings(season)
    by_team = {e["team"].pk: e for e in table}

    assert by_team[finisher_team.pk]["points"] == 20
    assert by_team[sprinter_team.pk]["points"] == 20
    assert table[0]["team"].pk == finisher_team.pk


def test_standings_include_mountain_points_in_total(db, make_team, make_rider, make_result, make_marker, make_crossing):
    season = make_season()
    team = make_team("ALP")

    race = make_race_in_week(season, 1, "Race One")
    make_result(race, make_rider("Finisher", team), position=3)
    score_race(race)

    marker = make_marker(race, kind=RaceMarker.Kind.MOUNTAIN,
                         category=RaceMarker.Category.CAT1)
    make_crossing(marker, make_rider("Climber", team), position=1)
    score_mountains(race)

    table = standings(season)

    assert table[0]["points"] == 12 + 8
    assert table[0]["mountain_points"] == 8


def test_standings_keep_sprint_and_mountain_points_separate(
    db, make_team, make_rider, make_result, make_marker, make_crossing,
):
    season = make_season()
    team = make_team("ALP")

    race = make_race_in_week(season, 1, "Race One")
    make_result(race, make_rider("Finisher", team), position=3)
    score_race(race)

    sprint = make_marker(race, name="Valley Sprint", weight=RaceMarker.Weight.STANDARD)
    make_crossing(sprint, make_rider("Sprinter", team), position=1)
    mountain = make_marker(race, name="Hilltop", kind=RaceMarker.Kind.MOUNTAIN)
    make_crossing(mountain, make_rider("Climber", team), position=1)
    score_sprints(race)
    score_mountains(race)

    entry = standings(season)[0]

    assert entry["sprint_points"] == 6
    assert entry["mountain_points"] == 6
    assert entry["points"] == 12 + 6 + 6


def test_team_with_only_mountain_points_appears_in_standings(db, make_team, make_rider, make_marker, make_crossing):
    season = make_season()
    team = make_team("ALP")

    race = make_race_in_week(season, 1, "Race One")
    marker = make_marker(race, kind=RaceMarker.Kind.MOUNTAIN)
    make_crossing(marker, make_rider("Climber", team), position=1)
    score_mountains(race)

    table = standings(season)
    by_team = {e["team"].pk: e for e in table}

    assert by_team[team.pk]["points"] == 6
    assert by_team[team.pk]["mountain_points"] == 6
    assert by_team[team.pk]["sprint_points"] == 0
    assert by_team[team.pk]["positions"] == {}


def test_mountain_points_do_not_count_in_countback(db, make_team, make_rider, make_result, make_marker, make_crossing):
    """Being first over a summit is not a 1st place for tie-breaking, the
    same rule a sprint win follows."""
    season = make_season()
    finisher_team = make_team("FIN")
    climber_team = make_team("CLM")

    race1 = make_race_in_week(season, 1, "Race One")
    make_result(race1, make_rider("Winner", finisher_team), position=1)
    score_race(race1)

    race2 = make_race_in_week(season, 2, "Race Two")
    marker1 = make_marker(race2, name="Top A", kind=RaceMarker.Kind.MOUNTAIN,
                          category=RaceMarker.Category.HC)
    make_crossing(marker1, make_rider("Climber A", climber_team), position=1)
    race3 = make_race_in_week(season, 3, "Race Three")
    marker2 = make_marker(race3, name="Top B", kind=RaceMarker.Kind.MOUNTAIN,
                          category=RaceMarker.Category.HC)
    make_crossing(marker2, make_rider("Climber B", climber_team), position=1)
    score_mountains(race2)
    score_mountains(race3)

    table = standings(season)
    by_team = {e["team"].pk: e for e in table}

    assert by_team[finisher_team.pk]["points"] == 20
    assert by_team[climber_team.pk]["points"] == 20
    assert by_team[climber_team.pk]["mountain_points"] == 20
    assert table[0]["team"].pk == finisher_team.pk


def test_table_resets_between_seasons(db, make_team, make_rider, make_result):
    season1 = make_season(number=1, starts_at=datetime(2027, 1, 4, tzinfo=dt_timezone.utc))
    # Season 1 runs twelve weeks from 2027-01-04, ending 2027-03-29 — season 2
    # must start no earlier than that to avoid Season.clean()'s overlap check.
    season2 = make_season(number=2, starts_at=datetime(2027, 3, 29, tzinfo=dt_timezone.utc))
    team = make_team("ALP")

    race1 = make_race_in_week(season1, 1, "Season 1 Race")
    make_result(race1, make_rider("Rider One", team), position=1)
    score_race(race1)

    table_s1 = standings(season1)
    table_s2 = standings(season2)

    assert table_s1[0]["points"] == 20
    assert table_s2 == []


def test_standings_include_gc_points(db, make_team, make_rider):
    from racing.models import RaceSquad, RaceSquadRider

    season = make_season()
    week = season.weeks.get(number=1)
    stage_race = StageRace.objects.create(name="Alpine Tour", week=week)
    stage1 = Race.objects.create(
        name="Alpine Tour — Stage 1",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.FINISHED,
        starts_at=week.starts_at,
        week=week,
        stage_race=stage_race,
        stage_number=1,
    )
    stage2 = Race.objects.create(
        name="Alpine Tour — Stage 2",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.FINISHED,
        starts_at=week.starts_at + timedelta(days=1),
        week=week,
        stage_race=stage_race,
        stage_number=2,
    )
    team = make_team("ALP")
    rider = make_rider("Rider One", team)
    squad = RaceSquad.objects.create(race=stage1, team=team)
    RaceSquadRider.objects.create(squad=squad, rider=rider, is_leader=True)
    RaceResult.objects.create(race=stage1, rider=rider, position=1, finish_time=100.0, group_time=100.0)
    RaceResult.objects.create(race=stage2, rider=rider, position=1, finish_time=100.0, group_time=100.0)

    score_race(stage1)
    score_race(stage2)
    score_general_classification(stage_race)

    table = standings(season)

    # Stage 1 (10, stage table) + stage 2 (10) + GC 1st place (40) = 60.
    assert table[0]["points"] == 10 + 10 + 40
