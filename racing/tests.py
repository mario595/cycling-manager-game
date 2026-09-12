from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from racing.adapters import to_engine_course, to_engine_rider, to_team_codes
from racing.models import Race, RaceLog, RaceResult, RaceSquad, RaceSquadRider
from racing.services import (
    SquadError,
    auto_pick_squad,
    previous_squad,
    set_squad,
    simulate_race,
    suggested_squad,
)
from riders.models import Rider
from schedule.models import Season, Week
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


MONDAY = datetime(2027, 3, 1, 0, 0, 0, tzinfo=dt_timezone.utc)


@pytest.fixture
def week(db) -> Week:
    season = Season.objects.create(number=1, starts_at=MONDAY)
    return Week.objects.create(
        season=season, number=1, starts_at=MONDAY, ends_at=MONDAY + timedelta(weeks=1),
    )


def test_race_without_a_week_saves_unchanged(db):
    race = Race.objects.create(
        name="Standalone Race",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=MONDAY,
    )

    assert race.week is None


def test_race_inside_its_week_saves(db, week):
    race = Race.objects.create(
        name="In Week Race",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=week.starts_at + timedelta(days=2),
        week=week,
    )

    assert race.week == week


def test_race_outside_its_week_is_rejected(db, week):
    with pytest.raises(ValidationError):
        Race.objects.create(
            name="Late Race",
            course=[{"length": 500.0, "gradient": 0.0}],
            starts_at=week.ends_at + timedelta(seconds=1),
            week=week,
        )


def test_race_at_the_exact_week_start_is_accepted(db, week):
    race = Race.objects.create(
        name="On Time Race",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=week.starts_at,
        week=week,
    )

    assert race.week == week


def test_race_day_is_derived_from_starts_at(db, week):
    race = Race.objects.create(
        name="Derived Day Race",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=week.starts_at + timedelta(days=2, hours=14),
        week=week,
    )

    assert race.race_day == (week.starts_at + timedelta(days=2)).date()


def test_two_races_on_one_day_of_one_week_are_rejected(db, week):
    Race.objects.create(
        name="First Race",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=week.starts_at + timedelta(days=2, hours=10),
        week=week,
    )

    with pytest.raises(IntegrityError):
        Race.objects.create(
            name="Second Race",
            course=[{"length": 500.0, "gradient": 0.0}],
            starts_at=week.starts_at + timedelta(days=2, hours=15),
            week=week,
        )


def test_two_races_on_different_days_of_one_week_are_accepted(db, week):
    Race.objects.create(
        name="Saturday Race",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=week.starts_at + timedelta(days=5),
        week=week,
    )
    Race.objects.create(
        name="Sunday Race",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=week.starts_at + timedelta(days=6),
        week=week,
    )

    assert Race.objects.filter(week=week).count() == 2


def test_two_weekless_races_on_the_same_date_are_accepted(db):
    Race.objects.create(
        name="First Weekless Race",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=MONDAY,
    )
    Race.objects.create(
        name="Second Weekless Race",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=MONDAY,
    )

    assert Race.objects.filter(week__isnull=True, race_day=MONDAY.date()).count() == 2


def test_a_team_cannot_have_two_squads_for_one_race(db, running_race, team):
    RaceSquad.objects.create(race=running_race, team=team)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            RaceSquad.objects.create(race=running_race, team=team)


def test_a_rider_cannot_appear_twice_in_a_squad(running_race, four_riders):
    squad = RaceSquad.objects.create(race=running_race, team=four_riders[0].team)
    RaceSquadRider.objects.create(squad=squad, rider=four_riders[0], is_leader=True)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            RaceSquadRider.objects.create(squad=squad, rider=four_riders[0])


def test_auto_pick_prefers_leaders_then_strength(db, team):
    # Six riders: one weak leader, one strong support, four mid-strength
    # support riders. The leader must win despite being weakest, and among
    # the rest the strongest three fill the squad, tiebroken by pk.
    weak_leader = Rider.objects.create(
        name="Weak Leader", team=team, role=Rider.Role.LEADER,
        climb=20, sprint=20, flat=20, resistance=20, positioning=20,
    )
    strong_support = Rider.objects.create(
        name="Strong Support", team=team, role=Rider.Role.SUPPORT,
        climb=90, sprint=90, flat=90, resistance=90, positioning=90,
    )
    mid_supports = [
        Rider.objects.create(
            name=f"Mid Support {i}", team=team, role=Rider.Role.SUPPORT,
            climb=50, sprint=50, flat=50, resistance=50, positioning=50,
        )
        for i in range(4)
    ]

    rider_ids, leader_id = auto_pick_squad(team)

    assert leader_id == weak_leader.pk
    assert rider_ids[0] == weak_leader.pk
    assert strong_support.pk in rider_ids
    # Three of the four mid-strength riders fill the rest, tiebroken by pk —
    # the lowest three pks among them, since they are all tied on strength.
    expected_mids = sorted(r.pk for r in mid_supports)[:2]
    for pk in expected_mids:
        assert pk in rider_ids
    assert len(rider_ids) == 4


def test_auto_pick_refuses_a_team_of_three(db, team):
    for i in range(3):
        Rider.objects.create(
            name=f"Rider {i}", team=team,
            climb=50, sprint=50, flat=50, resistance=50, positioning=50,
        )

    with pytest.raises(SquadError):
        auto_pick_squad(team)


def test_previous_squad_ignores_riders_who_left_the_team(db, team, four_riders, week):
    other_team = Team.objects.create(name="Team Beta", code="BET")
    earlier_race = Race.objects.create(
        name="Earlier Race",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=week.starts_at + timedelta(days=1),
        week=week,
    )
    squad = RaceSquad.objects.create(race=earlier_race, team=team)
    RaceSquadRider.objects.bulk_create([
        RaceSquadRider(squad=squad, rider=r, is_leader=(i == 0))
        for i, r in enumerate(four_riders)
    ])

    # One of the four riders transfers away before the next race is picked.
    four_riders[0].team = other_team
    four_riders[0].save()

    later_race = Race.objects.create(
        name="Later Race",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=week.starts_at + timedelta(days=2),
        week=week,
    )

    assert previous_squad(team, later_race) is None


@pytest.fixture
def scheduled_race(db) -> Race:
    return Race.objects.create(
        name="Scheduled Sprint",
        course=[{"length": 500.0, "gradient": 0.0}],
    )


def test_set_squad_replaces_the_previous_selection(scheduled_race, team, four_riders):
    other_four = [
        Rider.objects.create(
            name=f"Other Rider {i}", team=team,
            climb=50, sprint=50, flat=50, resistance=50, positioning=50,
        )
        for i in range(4)
    ]

    set_squad(scheduled_race, team, [r.pk for r in four_riders], four_riders[0].pk)
    set_squad(scheduled_race, team, [r.pk for r in other_four], other_four[0].pk)

    squad = RaceSquad.objects.get(race=scheduled_race, team=team)
    assert squad.members.count() == 4
    assert set(squad.members.values_list("rider_id", flat=True)) == {r.pk for r in other_four}


def test_set_squad_refuses_the_wrong_number_of_riders(scheduled_race, team, four_riders):
    with pytest.raises(SquadError):
        set_squad(scheduled_race, team, [r.pk for r in four_riders[:3]], four_riders[0].pk)


def test_set_squad_refuses_a_duplicate_rider(scheduled_race, team, four_riders):
    ids = [four_riders[0].pk, four_riders[0].pk, four_riders[1].pk, four_riders[2].pk]
    with pytest.raises(SquadError):
        set_squad(scheduled_race, team, ids, four_riders[0].pk)


def test_set_squad_refuses_a_rider_from_another_team(scheduled_race, team, four_riders):
    other_team = Team.objects.create(name="Team Gamma", code="GAM")
    outsider = Rider.objects.create(
        name="Outsider", team=other_team,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    ids = [r.pk for r in four_riders[:3]] + [outsider.pk]

    with pytest.raises(SquadError):
        set_squad(scheduled_race, team, ids, four_riders[0].pk)


def test_set_squad_refuses_a_leader_not_in_the_squad(scheduled_race, team, four_riders):
    outsider = Rider.objects.create(
        name="Not Selected", team=team,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    with pytest.raises(SquadError):
        set_squad(scheduled_race, team, [r.pk for r in four_riders], outsider.pk)


def test_set_squad_refuses_a_race_that_has_started(running_race, team, four_riders):
    with pytest.raises(SquadError):
        set_squad(running_race, team, [r.pk for r in four_riders], four_riders[0].pk)


def test_suggested_squad_falls_back_from_saved_to_previous_to_auto(db, team, week):
    riders = [
        Rider.objects.create(
            name=f"Rider {i}", team=team, role=Rider.Role.LEADER if i == 0 else Rider.Role.SUPPORT,
            climb=50, sprint=50, flat=50, resistance=50, positioning=50,
        )
        for i in range(4)
    ]
    race_one = Race.objects.create(
        name="Race One",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=week.starts_at + timedelta(days=1),
        week=week,
    )
    race_two = Race.objects.create(
        name="Race Two",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=week.starts_at + timedelta(days=2),
        week=week,
    )
    race_three = Race.objects.create(
        name="Race Three",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=week.starts_at + timedelta(days=3),
        week=week,
    )

    # No squad anywhere yet: falls all the way to the auto-pick.
    auto_ids, auto_leader = auto_pick_squad(team)
    assert suggested_squad(race_one, team) == (auto_ids, auto_leader)

    # A squad saved for race_one: race_two, unpicked, falls back to it.
    set_squad(race_one, team, [r.pk for r in riders], riders[0].pk)
    assert suggested_squad(race_two, team) == ([r.pk for r in riders], riders[0].pk)

    # race_two now has its own saved squad, with a different leader: that
    # exact selection is returned, not race_one's.
    set_squad(race_two, team, [r.pk for r in riders], riders[1].pk)
    assert suggested_squad(race_two, team) == ([r.pk for r in riders], riders[1].pk)
    assert suggested_squad(race_three, team) == ([r.pk for r in riders], riders[1].pk)
