from __future__ import annotations

import pytest
from django.utils import timezone

from racing.adapters import to_engine_course, to_engine_rider, to_team_codes
from racing.models import Race, RaceLog, RaceResult
from racing.services import simulate_race
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


@pytest.fixture
def four_riders(db, team) -> list[Rider]:
    return [
        Rider.objects.create(
            name=f"Rider {i}",
            team=team,
            role=Rider.Role.LEADER if i == 0 else Rider.Role.SUPPORT,
            climb=60,
            sprint=60,
            flat=60,
            resistance=60,
            positioning=60,
        )
        for i in range(4)
    ]


@pytest.fixture
def running_race(db) -> Race:
    return Race.objects.create(
        name="Tiny Sprint",
        course=[{"length": 500.0, "gradient": 0.0}],
        status=Race.Status.RUNNING,
    )


def test_simulate_race_writes_log_and_results(running_race, four_riders):
    game_time = timezone.now()

    results = simulate_race(running_race, game_time=game_time)

    running_race.refresh_from_db()
    assert running_race.status == Race.Status.FINISHED
    assert running_race.finished_at == game_time

    log = RaceLog.objects.get(race=running_race)
    assert log.tick_count > 0

    positions = sorted(
        RaceResult.objects.filter(race=running_race).values_list("position", flat=True)
    )
    assert positions == [1, 2, 3, 4]
    assert len(results) == 4


def test_simulate_race_refuses_finished_race(running_race, four_riders):
    simulate_race(running_race, game_time=timezone.now())
    running_race.refresh_from_db()

    with pytest.raises(ValueError):
        simulate_race(running_race, game_time=timezone.now())
