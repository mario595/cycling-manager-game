from __future__ import annotations

import pytest

from competitions.services import prizes_by_team
from competitions.scoring import prize_for
from racing.models import Race
from riders.models import Rider


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