from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone

from competitions.services import score_general_classification, score_race, standings
from racing.models import Race, RaceResult, StageRace
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
