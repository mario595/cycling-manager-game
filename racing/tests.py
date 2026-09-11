from __future__ import annotations

import pytest

from racing.adapters import to_engine_course, to_engine_rider, to_team_codes
from racing.models import Race
from riders.models import Rider
from teams.models import Team


@pytest.fixture
def team(db) -> Team:
    return Team.objects.create(name="Team Alpha", code="ALP", primary_colour="#FF0000")


@pytest.fixture
def rider(db, team) -> Rider:
    return Rider.objects.create(
        name="Climber One",
        team=team,
        role=Rider.Role.LEADER,
        climb=94,
        sprint=30,
        flat=40,
        resistance=80,
        positioning=52,
    )


def test_rider_converts_to_engine_dataclass(rider):
    engine_rider = to_engine_rider(rider)

    assert engine_rider.name == "Climber One"
    assert engine_rider.id == str(rider.pk)
    assert engine_rider.role == "leader"
    assert engine_rider.attributes.climb == 94
    assert engine_rider.attributes.positioning == 52


def test_teamless_rider_becomes_own_team(db):
    free_agent = Rider.objects.create(
        name="Free Agent",
        climb=50,
        sprint=50,
        flat=50,
        resistance=50,
        positioning=50,
    )

    engine_rider = to_engine_rider(free_agent)

    # The engine's own default: a rider with no team rides as a team of one.
    assert engine_rider.team_id == engine_rider.id


def test_course_json_converts_to_engine_course(db):
    race = Race.objects.create(
        name="Test Stage",
        course=[
            {"length": 7000.0, "gradient": 0.0},
            {"length": 1000.0, "gradient": 5.0},
        ],
    )

    course = to_engine_course(race)

    assert len(course.segments) == 2
    assert course.total_distance == 8000.0
    assert course.segments[1].gradient == 5.0


def test_team_codes_match_player_format(team):
    codes = to_team_codes([team])

    assert codes[str(team.pk)]["code"] == "ALP"
    assert codes[str(team.pk)]["colour"] == "#FF0000"


def test_race_defaults_to_scheduled_and_unscheduled(db):
    race = Race.objects.create(name="Test Stage", course=[{"length": 1000.0, "gradient": 0.0}])

    assert race.status == Race.Status.SCHEDULED
    assert race.starts_at is None
    assert race.finished_at is None
