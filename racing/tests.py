from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone as dt_timezone

import brotli
import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from racing.adapters import to_engine_course, to_engine_rider, to_team_codes
from racing.models import (
    MarkerCrossing,
    Race,
    RaceLog,
    RaceMarker,
    RaceResult,
    RaceSquad,
    RaceSquadRider,
)
from racing.services import (
    SquadError,
    auto_pick_squad,
    course_training_attribute,
    create_race,
    previous_squad,
    riders_who_raced,
    riders_who_started,
    set_squad,
    simulate_race,
    suggested_squad,
)
from riders.models import Rider
from riders.services import FRESHNESS_FLOOR
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
        climb=94,
        sprint=30,
        flat=40,
        resistance=80,
        positioning=52,
    )


def test_rider_converts_to_engine_dataclass(rider):
    engine_rider = to_engine_rider(rider, role="leader")

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

    engine_rider = to_engine_rider(free_agent, role="support")

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
    first = RaceMarker.objects.create(
        race=race, kind=RaceMarker.Kind.SPRINT, name="First", distance=3000.0
    )
    second = RaceMarker.objects.create(
        race=race, kind=RaceMarker.Kind.MOUNTAIN, name="Summit", distance=7500.0
    )

    course = to_engine_course(race, [first, second])

    assert len(course.segments) == 2
    assert course.total_distance == 8000.0
    assert course.segments[1].gradient == 5.0
    assert [(m.kind.value, m.name, m.distance) for m in course.markers] == [
        ("sprint", "First", 3000.0),
        ("mountain", "Summit", 7500.0),
    ]


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
    # The log is brotli-compressed: one header line followed by the samples.
    with log.file.open("rb") as fh:
        text = brotli.decompress(fh.read()).decode()
    lines = text.splitlines()
    assert log.sample_count == len(lines) - 1
    assert log.tick_interval == 2
    assert log.size_bytes == log.file.size
    assert log.file.name.endswith(".jsonl.br")

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


def test_auto_pick_takes_the_strongest_four_tiebroken_by_pk(db, team):
    # Six riders: one strong, four mid-strength, one weak. The strong rider
    # must be picked and lead; the weak rider must be excluded; three of the
    # four mid-strength riders fill the rest, tiebroken by pk.
    strong = Rider.objects.create(
        name="Strong", team=team,
        climb=90, sprint=90, flat=90, resistance=90, positioning=90,
    )
    mids = [
        Rider.objects.create(
            name=f"Mid {i}", team=team,
            climb=50, sprint=50, flat=50, resistance=50, positioning=50,
        )
        for i in range(4)
    ]
    weak = Rider.objects.create(
        name="Weak", team=team,
        climb=20, sprint=20, flat=20, resistance=20, positioning=20,
    )

    rider_ids, leader_id = auto_pick_squad(team)

    assert leader_id == strong.pk
    assert rider_ids[0] == strong.pk
    assert weak.pk not in rider_ids
    # Three of the four mid-strength riders fill the rest, tiebroken by pk —
    # the lowest three pks among them, since they are all tied on strength.
    expected_mids = sorted(r.pk for r in mids)[:3]
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
            name=f"Rider {i}", team=team,
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


def test_only_selected_riders_appear_in_the_results(running_race):
    team_one = Team.objects.create(name="Team One", code="ONE")
    team_two = Team.objects.create(name="Team Two", code="TWO")
    squad_one = [
        Rider.objects.create(
            name=f"One {i}", team=team_one,
            climb=60, sprint=60, flat=60, resistance=60, positioning=60,
        )
        for i in range(4)
    ]
    bench_one = [
        Rider.objects.create(
            name=f"One Bench {i}", team=team_one,
            climb=40, sprint=40, flat=40, resistance=40, positioning=40,
        )
        for i in range(2)
    ]
    squad_two = [
        Rider.objects.create(
            name=f"Two {i}", team=team_two,
            climb=60, sprint=60, flat=60, resistance=60, positioning=60,
        )
        for i in range(4)
    ]

    # set_squad refuses a race that has already started, so pick both
    # squads while it is still scheduled, then flip it to running the same
    # way the tick would before simulating.
    running_race.status = Race.Status.SCHEDULED
    running_race.save(update_fields=["status"])
    set_squad(running_race, team_one, [r.pk for r in squad_one], squad_one[0].pk)
    set_squad(running_race, team_two, [r.pk for r in squad_two], squad_two[0].pk)
    running_race.status = Race.Status.RUNNING
    running_race.save(update_fields=["status"])

    simulate_race(running_race, game_time=timezone.now())

    result_rider_ids = set(RaceResult.objects.filter(race=running_race).values_list("rider_id", flat=True))
    assert result_rider_ids == {r.pk for r in squad_one + squad_two}
    assert RaceResult.objects.filter(race=running_race).count() == 8
    for bench_rider in bench_one:
        assert bench_rider.pk not in result_rider_ids


def test_simulate_race_excludes_a_squad_member_sold_before_the_race_runs(running_race, team, four_riders):
    # A listed rider keeps racing while the auction is live (spec item 9),
    # so a manager will leave them in a saved squad — but if the auction
    # resolves and moves the rider to the buyer before this race's own
    # tick, the squad row still points at the seller. Racing them anyway
    # would let the engine and score_race/prizes_by_team (both keyed off
    # the rider's CURRENT team_id) credit the result to the buyer, not the
    # team that actually fielded them.
    running_race.status = Race.Status.SCHEDULED
    running_race.save(update_fields=["status"])
    set_squad(running_race, team, [r.pk for r in four_riders], four_riders[0].pk)
    running_race.status = Race.Status.RUNNING
    running_race.save(update_fields=["status"])

    buyer = Team.objects.create(name="Team Bravo", code="BRA")
    sold = four_riders[0]
    sold.team = buyer
    sold.save(update_fields=["team"])

    results = simulate_race(running_race, game_time=timezone.now())

    assert len(results) == 3
    assert not RaceResult.objects.filter(race=running_race, rider=sold).exists()
    assert {r.rider_id for r in results} == {r.pk for r in four_riders[1:]}


def test_simulate_race_promotes_a_leader_when_the_picked_one_is_sold(running_race, team, four_riders):
    # The engine requires exactly one leader per team present
    # (race_engine.models.validate_team_leaders) — dropping the sold
    # leader without promoting a replacement would crash the race for
    # every team, not just leave the seller a rider short.
    running_race.status = Race.Status.SCHEDULED
    running_race.save(update_fields=["status"])
    leader = four_riders[0]
    set_squad(running_race, team, [r.pk for r in four_riders], leader.pk)
    running_race.status = Race.Status.RUNNING
    running_race.save(update_fields=["status"])

    buyer = Team.objects.create(name="Team Bravo", code="BRA")
    leader.team = buyer
    leader.save(update_fields=["team"])

    results = simulate_race(running_race, game_time=timezone.now())

    # No exception, and the squad's own stored selection is untouched —
    # this is a simulation-time-only workaround.
    assert len(results) == 3
    squad = RaceSquad.objects.get(race=running_race, team=team)
    assert squad.members.get(rider=four_riders[1]).is_leader is False


def test_the_squad_leader_races_as_leader(running_race, team, four_riders):
    # Name a rider other than the first as this race's leader. set_squad
    # refuses a started race, so pick the squad while scheduled, then flip
    # to running like the tick would.
    running_race.status = Race.Status.SCHEDULED
    running_race.save(update_fields=["status"])
    set_squad(running_race, team, [r.pk for r in four_riders], four_riders[1].pk)
    running_race.status = Race.Status.RUNNING
    running_race.save(update_fields=["status"])

    simulate_race(running_race, game_time=timezone.now())

    log = RaceLog.objects.get(race=running_race)
    with log.file.open("rb") as fh:
        first_line = json.loads(brotli.decompress(fh.read()).decode().splitlines()[0])
    leader_entry = next(
        e for e in first_line["riders"] if e["id"] == str(four_riders[1].pk)
    )
    assert leader_entry["role"] == "leader"


def test_a_team_with_no_squad_gets_one_at_race_time(running_race, four_riders):
    assert not RaceSquad.objects.filter(race=running_race).exists()

    simulate_race(running_race, game_time=timezone.now())

    squad = RaceSquad.objects.get(race=running_race, team=four_riders[0].team)
    assert squad.is_auto_picked is True
    assert squad.members.count() == 4


def test_a_team_of_three_is_skipped_rather_than_crashing_the_race(running_race, team, four_riders):
    understaffed_team = Team.objects.create(name="Understaffed", code="UND")
    for i in range(3):
        Rider.objects.create(
            name=f"Thin {i}", team=understaffed_team,
            climb=50, sprint=50, flat=50, resistance=50, positioning=50,
        )

    results = simulate_race(running_race, game_time=timezone.now())

    assert not RaceSquad.objects.filter(race=running_race, team=understaffed_team).exists()
    assert len(results) == 4


def test_course_training_attribute_buckets():
    mountain = [{"length": 50000.0, "gradient": 3.0}]
    long_flat = [{"length": 250000.0, "gradient": 0.0}]
    short_flat = [{"length": 50000.0, "gradient": 0.0}]
    mid_flat = [{"length": 150000.0, "gradient": 0.0}]

    assert course_training_attribute(mountain) == "climb"
    assert course_training_attribute(long_flat) == "resistance"
    assert course_training_attribute(short_flat) == "sprint"
    assert course_training_attribute(mid_flat) == "flat"
    # No segments, or no total length, must not divide by zero.
    assert course_training_attribute([]) == "flat"


def test_riders_who_raced_groups_by_rider(db, week, team):
    racer = Rider.objects.create(
        name="Twice Racer", team=team,
        climb=60, sprint=60, flat=60, resistance=60, positioning=60,
    )
    abandoned = Rider.objects.create(
        name="Abandoned", team=team,
        climb=60, sprint=60, flat=60, resistance=60, positioning=60,
    )
    race_one = Race.objects.create(
        name="Short Flat", course=[{"length": 50000.0, "gradient": 0.0}],
        starts_at=week.starts_at + timedelta(days=1), week=week,
    )
    race_two = Race.objects.create(
        name="Short Climber", course=[{"length": 50000.0, "gradient": 3.0}],
        starts_at=week.starts_at + timedelta(days=2), week=week,
    )
    RaceResult.objects.create(race=race_one, rider=racer, position=1, finish_time=1000.0)
    RaceResult.objects.create(race=race_two, rider=racer, position=1, finish_time=2000.0)
    RaceResult.objects.create(race=race_one, rider=abandoned, position=2, finish_time=None)

    raced = riders_who_raced(week)

    assert set(raced[racer.pk]) == {"sprint", "climb"}
    assert abandoned.pk not in raced


def test_riders_who_started_includes_non_finishers(db, week, team):
    finisher = Rider.objects.create(
        name="Finisher", team=team,
        climb=60, sprint=60, flat=60, resistance=60, positioning=60,
    )
    cut = Rider.objects.create(
        name="Cut", team=team,
        climb=60, sprint=60, flat=60, resistance=60, positioning=60,
    )
    other_week_rider = Rider.objects.create(
        name="Other Week", team=team,
        climb=60, sprint=60, flat=60, resistance=60, positioning=60,
    )
    race = Race.objects.create(
        name="Short Flat", course=[{"length": 50000.0, "gradient": 0.0}],
        starts_at=week.starts_at + timedelta(days=1), week=week,
    )
    RaceResult.objects.create(race=race, rider=finisher, position=1, finish_time=1000.0)
    RaceResult.objects.create(race=race, rider=cut, position=2, finish_time=None)

    other_season = Season.objects.create(number=2, starts_at=MONDAY + timedelta(weeks=1))
    other_week = Week.objects.create(
        season=other_season, number=1, starts_at=MONDAY + timedelta(weeks=1),
        ends_at=MONDAY + timedelta(weeks=2),
    )
    other_race = Race.objects.create(
        name="Other Week Race", course=[{"length": 50000.0, "gradient": 0.0}],
        starts_at=other_week.starts_at + timedelta(days=1), week=other_week,
    )
    RaceResult.objects.create(race=other_race, rider=other_week_rider, position=1, finish_time=1000.0)

    started = riders_who_started(week)

    assert started == {finisher.pk, cut.pk}


def test_to_engine_rider_scales_attributes_by_freshness(rider):
    fresh = to_engine_rider(rider, role="leader", freshness_scale=1.0)
    tired = to_engine_rider(rider, role="leader", freshness_scale=0.80)

    assert tired.attributes.climb < fresh.attributes.climb
    assert tired.attributes.sprint < fresh.attributes.sprint
    assert tired.attributes.positioning < fresh.attributes.positioning
    assert tired.attributes.resistance < fresh.attributes.resistance
    assert tired.attributes.flat < fresh.attributes.flat


def test_to_engine_rider_defaults_to_no_scaling(rider):
    """Existing callers that do not pass freshness_scale must see
    the stored attribute values unchanged."""
    unscaled = to_engine_rider(rider, role="support")

    assert unscaled.attributes.climb == 94
    assert unscaled.attributes.positioning == 52


def test_to_engine_rider_never_scales_below_engine_minimum(db, team):
    """A rider at attribute 1 with the floor multiplier (0.80) must
    still produce 1, not 0 — the engine validates its range and a 0
    would raise mid-race."""
    minimal = Rider.objects.create(
        name="Minimal", team=team,
        climb=1, sprint=1, flat=1, resistance=1, positioning=1,
    )

    # floor multiplier is 0.80; round(1 * 0.80) = 1, already >= 1.
    # test with an even smaller scale to prove the clamp works.
    scaled = to_engine_rider(minimal, role="support", freshness_scale=0.10)

    assert scaled.attributes.climb == 1
    assert scaled.attributes.sprint == 1
    assert scaled.attributes.flat == 1
    assert scaled.attributes.resistance == 1
    assert scaled.attributes.positioning == 1


def test_simulate_race_deducts_freshness_from_finishers(running_race, four_riders):
    simulate_race(running_race, game_time=timezone.now())

    for rider in four_riders:
        rider.refresh_from_db()
        assert rider.freshness == 100 - 25


def test_simulate_race_deducts_freshness_from_non_finishers(running_race, four_riders, monkeypatch):
    # The engine now produces real non-finishers (cut by the time limit),
    # not just abandons — inject one through the adapter seam and confirm
    # simulate_race charges every starter, finisher or not (broom-wagon-
    # time-cut spec, In scope 5).
    from pathlib import Path
    from types import SimpleNamespace

    states = [
        SimpleNamespace(finish_time=100.0, position=1000.0, rider=SimpleNamespace(id=str(r.pk)))
        for r in four_riders
    ]
    states[-1].finish_time = None

    def fake_run_race(riders, course, log_path, *args, **kwargs):
        Path(log_path).touch()
        return states, 0, 2

    monkeypatch.setattr("racing.services.run_race_via_adapter", fake_run_race)

    simulate_race(running_race, game_time=timezone.now())

    for rider in four_riders:
        rider.refresh_from_db()
        assert rider.freshness == 100 - 25


def test_simulate_race_orders_non_finishers_furthest_first(running_race, four_riders, monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace

    states = [
        SimpleNamespace(finish_time=10.0, position=5000.0, rider=SimpleNamespace(id=str(four_riders[0].pk))),
        SimpleNamespace(finish_time=None, position=3000.0, rider=SimpleNamespace(id=str(four_riders[1].pk))),
        SimpleNamespace(finish_time=None, position=8000.0, rider=SimpleNamespace(id=str(four_riders[2].pk))),
        SimpleNamespace(finish_time=None, position=1000.0, rider=SimpleNamespace(id=str(four_riders[3].pk))),
    ]

    def fake_run_race(riders, course, log_path, *args, **kwargs):
        Path(log_path).touch()
        return states, 0, 2

    monkeypatch.setattr("racing.services.run_race_via_adapter", fake_run_race)

    simulate_race(running_race, game_time=timezone.now())

    positions = {
        r.rider_id: r.position
        for r in RaceResult.objects.filter(race=running_race)
    }
    assert positions[four_riders[2].pk] < positions[four_riders[1].pk] < positions[four_riders[3].pk]


def test_auto_pick_prefers_fresher_rider_of_equal_strength(db, team):
    fresh = Rider.objects.create(
        name="Fresh Strong", team=team,
        climb=90, sprint=90, flat=90, resistance=90, positioning=90,
    )
    tired = Rider.objects.create(
        name="Tired Strong", team=team,
        climb=90, sprint=90, flat=90, resistance=90, positioning=90,
    )
    tired.freshness = FRESHNESS_FLOOR
    tired.save(update_fields=["freshness"])
    for i in range(2):
        Rider.objects.create(
            name=f"Filler {i}", team=team,
            climb=20, sprint=20, flat=20, resistance=20, positioning=20,
        )

    rider_ids, leader_id = auto_pick_squad(team)

    assert leader_id == fresh.pk
    assert rider_ids[:2] == [fresh.pk, tired.pk]


def test_auto_pick_still_prefers_much_stronger_tired_rider(db, team):
    strong = Rider.objects.create(
        name="Strong Tired", team=team,
        climb=90, sprint=90, flat=90, resistance=90, positioning=90,
    )
    strong.freshness = FRESHNESS_FLOOR
    strong.save(update_fields=["freshness"])
    medium = Rider.objects.create(
        name="Medium Fresh", team=team,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    for i in range(2):
        Rider.objects.create(
            name=f"Weak {i}", team=team,
            climb=20, sprint=20, flat=20, resistance=20, positioning=20,
        )

    rider_ids, leader_id = auto_pick_squad(team)

    assert leader_id == strong.pk
    assert rider_ids[0] == strong.pk
    assert rider_ids[1] == medium.pk


def test_tired_riders_finish_worse_than_fresh_ones_on_the_same_seed(db):
    """The likeliest failure mode for this feature is the penalty silently
    not applying — the numbers all move on screen but the scaled attributes
    never reach the engine. Simulating the same course twice with the same
    seed, once with one team at the floor, is what catches it: engine
    randomness is identical between the runs, so any ordering change is
    caused by the penalty."""
    tired_team = Team.objects.create(name="Tired Team", code="TIR")
    fresh_team = Team.objects.create(name="Fresh Team", code="FRE")
    for name, team in [("Tired", tired_team), ("Fresh", fresh_team)]:
        for i in range(4):
            Rider.objects.create(
                name=f"{name} {i}", team=team,
                climb=90, sprint=90, flat=90, resistance=90, positioning=90,
            )
    course = [{"length": 500.0, "gradient": 0.0}]
    both_fresh = Race.objects.create(name="Both Fresh", course=course, seed=12345)
    race_tired = Race.objects.create(name="Tired Team", course=course, seed=12345)

    simulate_race(both_fresh, game_time=timezone.now())

    Rider.objects.filter(team=tired_team).update(freshness=FRESHNESS_FLOOR)
    simulate_race(race_tired, game_time=timezone.now())

    def best_position(race, team) -> int:
        return min(
            RaceResult.objects.filter(race=race, rider__team=team)
            .values_list("position", flat=True)
        )

    fresh_min = best_position(both_fresh, tired_team)
    tired_min = best_position(race_tired, tired_team)
    fresh_team_min = best_position(race_tired, fresh_team)

    assert fresh_min < tired_min
    assert fresh_team_min < tired_min


def test_marker_beyond_course_is_rejected(db):
    race = Race.objects.create(
        name="Big Hill",
        course=[{"length": 1000.0, "gradient": 0.0}],
    )

    with pytest.raises(ValidationError):
        RaceMarker.objects.create(
            race=race,
            kind=RaceMarker.Kind.SPRINT,
            name="Past the top",
            distance=1500.0,
        )


def test_marker_with_blank_name_is_rejected(db):
    race = Race.objects.create(
        name="Flat Day",
        course=[{"length": 1000.0, "gradient": 0.0}],
    )

    with pytest.raises(ValidationError):
        RaceMarker.objects.create(
            race=race,
            kind=RaceMarker.Kind.SPRINT,
            name="   ",
            distance=500.0,
        )


def test_markers_order_by_distance(db):
    race = Race.objects.create(
        name="Ordered",
        course=[{"length": 5000.0, "gradient": 0.0}],
    )
    RaceMarker.objects.create(
        race=race, kind=RaceMarker.Kind.SPRINT, name="Later", distance=4000.0
    )
    RaceMarker.objects.create(
        race=race, kind=RaceMarker.Kind.SPRINT, name="First", distance=1000.0
    )
    RaceMarker.objects.create(
        race=race, kind=RaceMarker.Kind.SPRINT, name="Second", distance=2500.0
    )

    assert [m.name for m in race.markers.all()] == ["First", "Second", "Later"]


def test_crossing_position_is_unique_per_marker(db, team):
    race = Race.objects.create(
        name="Sprint Day",
        course=[{"length": 5000.0, "gradient": 0.0}],
    )
    marker = RaceMarker.objects.create(
        race=race, kind=RaceMarker.Kind.SPRINT, name="Line", distance=4000.0
    )
    first = Rider.objects.create(
        name="Alpha", team=team, climb=50, sprint=50, flat=50, resistance=50, positioning=50
    )
    second = Rider.objects.create(
        name="Beta", team=team, climb=50, sprint=50, flat=50, resistance=50, positioning=50
    )
    MarkerCrossing.objects.create(marker=marker, rider=first, position=1, crossed_at=100.0)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            MarkerCrossing.objects.create(marker=marker, rider=second, position=1, crossed_at=101.0)


def test_create_race_creates_its_markers(db):
    race = create_race(
        name="Marked Stage",
        course=[{"length": 5000.0, "gradient": 0.0}],
        markers=[
            {"kind": "sprint", "name": "First", "distance": 1000.0},
            {"kind": "mountain", "name": "Summit", "distance": 4500.0},
        ],
    )

    assert list(race.markers.values_list("kind", "name", "distance")) == [
        ("sprint", "First", 1000.0),
        ("mountain", "Summit", 4500.0),
    ]


def test_marker_weight_defaults_to_standard(db):
    race = Race.objects.create(
        name="Flat Day",
        course=[{"length": 1000.0, "gradient": 0.0}],
    )
    marker = RaceMarker.objects.create(
        race=race, kind=RaceMarker.Kind.SPRINT, name="Mid-line", distance=500.0,
    )

    assert marker.weight == RaceMarker.Weight.STANDARD


def test_create_race_stores_marker_weight(db):
    race = create_race(
        name="Marked Stage",
        course=[{"length": 5000.0, "gradient": 0.0}],
        markers=[
            {"kind": "sprint", "name": "First", "distance": 1000.0, "weight": "major"},
        ],
    )

    assert race.markers.get().weight == RaceMarker.Weight.MAJOR


def test_create_race_without_weight_gives_standard(db):
    race = create_race(
        name="Marked Stage",
        course=[{"length": 5000.0, "gradient": 0.0}],
        markers=[
            {"kind": "mountain", "name": "Summit", "distance": 4500.0},
        ],
    )

    assert race.markers.get().weight == RaceMarker.Weight.STANDARD


def test_loader_weights_match_race_marker_weights():
    from schedule.loaders import MARKER_WEIGHTS

    assert set(MARKER_WEIGHTS) == set(RaceMarker.Weight.values)


def test_simulate_race_records_every_crossing_in_order(running_race, four_riders):
    marker = RaceMarker.objects.create(
        race=running_race, kind=RaceMarker.Kind.SPRINT, name="Mid-line", distance=250.0
    )

    simulate_race(running_race, game_time=timezone.now())

    crossings = list(marker.crossings.all())
    assert len(crossings) == 4
    assert [c.position for c in crossings] == [1, 2, 3, 4]
    assert [c.crossed_at for c in crossings] == sorted(c.crossed_at for c in crossings)


def test_finish_line_marker_matches_the_result_order(running_race, four_riders, monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace

    marker = RaceMarker.objects.create(
        race=running_race, kind=RaceMarker.Kind.SPRINT, name="Line", distance=500.0
    )
    # The finish times tie (both 100.0), so the result order follows the
    # states' position key: rider 1 (position 20) places ahead of rider 0
    # (position 10). The marker_times say the opposite — rider 0 crossed at
    # 110, rider 1 at 120 — so a naively interpolated order would disagree
    # with the results. By D5 the finish-line marker's crossings must follow
    # the result order regardless.
    states = [
        SimpleNamespace(
            finish_time=100.0, position=10.0,
            rider=SimpleNamespace(id=str(four_riders[0].pk)), marker_times={0: 110.0},
        ),
        SimpleNamespace(
            finish_time=100.0, position=20.0,
            rider=SimpleNamespace(id=str(four_riders[1].pk)), marker_times={0: 120.0},
        ),
        SimpleNamespace(
            finish_time=None, position=999.0,
            rider=SimpleNamespace(id=str(four_riders[2].pk)), marker_times={},
        ),
        SimpleNamespace(
            finish_time=None, position=500.0,
            rider=SimpleNamespace(id=str(four_riders[3].pk)), marker_times={},
        ),
    ]

    def fake_run_race(riders, course, log_path, *args, **kwargs):
        Path(log_path).touch()
        return states, 0, 2

    monkeypatch.setattr("racing.services.run_race_via_adapter", fake_run_race)

    simulate_race(running_race, game_time=timezone.now())

    crossings = list(marker.crossings.order_by("position"))
    assert [c.rider.pk for c in crossings] == [four_riders[1].pk, four_riders[0].pk]
    assert [c.crossed_at for c in crossings] == [100.0, 100.0]


def test_race_without_markers_records_no_crossings(running_race, four_riders):
    simulate_race(running_race, game_time=timezone.now())

    assert MarkerCrossing.objects.filter(marker__race=running_race).count() == 0
