from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone

import pytest

from competitions.services import prizes_by_team
from competitions.scoring import prize_for, stage_prize_for
from racing.models import Race, StageRace
from riders.models import Rider
from schedule.models import Season, Week


def test_every_placed_rider_is_paid(race, make_team, make_rider, make_result):
    team = make_team("ALP")
    make_result(race, make_rider("Second Placed", team), position=2)
    make_result(race, make_rider("Fifth Placed", team), position=5)

    prizes = prizes_by_team(race)

    assert prizes == {
        team.pk: [(2, prize_for(2)), (5, prize_for(5))],
    }


def test_non_finishers_are_never_paid(race, make_team, make_rider, make_result):
    team = make_team("ALP")
    make_result(race, make_rider("Winner", team), position=1)
    make_result(race, make_rider("Abandoned", team), position=2, finish_time=None)

    prizes = prizes_by_team(race)

    assert prizes == {team.pk: [(1, prize_for(1))]}


def test_rider_without_a_team_is_skipped(db, race, make_team, make_rider, make_result):
    team = make_team("ALP")
    make_result(race, make_rider("Winner", team), position=1)
    free_agent = Rider.objects.create(
        name="Free Agent", team=None,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    make_result(race, free_agent, position=2)

    prizes = prizes_by_team(race)

    assert prizes == {team.pk: [(1, prize_for(1))]}


def test_positions_outside_the_table_pay_nothing(race, make_team, make_rider, make_result):
    team = make_team("ALP")
    make_result(race, make_rider("Winner", team), position=1)
    make_result(race, make_rider("Eleventh", team), position=11)

    prizes = prizes_by_team(race)

    assert prizes == {team.pk: [(1, prize_for(1))]}


def test_unfinished_race_raises(db):
    race = Race.objects.create(
        name="Not Yet Run",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.SCHEDULED,
    )

    with pytest.raises(ValueError):
        prizes_by_team(race)


def test_stage_prizes_from_stage_table(db, make_team, make_rider, make_result):
    starts_at = datetime(2027, 1, 4, tzinfo=dt_timezone.utc)  # a Monday
    season = Season.objects.create(number=1, starts_at=starts_at)
    week = Week.objects.create(
        season=season, number=1, starts_at=starts_at, ends_at=starts_at + timedelta(weeks=1),
    )
    stage_race = StageRace.objects.create(name="Alpine Tour", week=week)
    stage = Race.objects.create(
        name="Alpine Tour — Stage 1",
        course=[{"length": 40000.0, "gradient": 0.0}],
        status=Race.Status.FINISHED,
        starts_at=week.starts_at,
        week=week,
        stage_race=stage_race,
        stage_number=1,
    )
    team = make_team("ALP")
    make_result(stage, make_rider("Rider One", team), position=1)

    prizes = prizes_by_team(stage)

    assert prizes == {team.pk: [(1, stage_prize_for(1))]}
    assert prizes[team.pk][0][1] != prize_for(1)  # the one-day table's 1st-place amount