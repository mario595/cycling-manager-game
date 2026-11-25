from __future__ import annotations

from datetime import timedelta

import pytest

import world.services as world_services
from accounts.models import User
from competitions.models import RacePoints
from economy.models import SalaryReviewReport
from racing.models import Race, RaceResult
from riders.models import Departure, Rider, RiderAttributeSnapshot
from riders.pricing import weekly_salary_for
from schedule.models import SEASON_WEEKS, Season, SeasonTransition, Week
from staff.generation import TRAINERS_PER_SEASON_BOUNDARY
from staff.models import Trainer, TrainingWeekReport
from staff.services import set_focus
from teams.models import Team
from teams.services import ROSTER_SIZE
from world.clocks import MockClock
from world.models import GameClock
from world.services import get_clock, now, tick


def make_season_with_weeks(number: int, starts_at) -> Season:
    season = Season.objects.create(number=number, starts_at=starts_at)
    for week_number in range(1, SEASON_WEEKS + 1):
        week_start = season.starts_at + timedelta(weeks=week_number - 1)
        Week.objects.create(
            season=season,
            number=week_number,
            starts_at=week_start,
            ends_at=week_start + timedelta(weeks=1),
        )
    return season


@pytest.fixture
def team(db) -> Team:
    return Team.objects.create(name="Team Alpha", code="ALP", primary_colour="#FF0000")


def _give_a_manager(team: Team) -> Team:
    """Make `team` human-managed, so the AI management (#45) leaves its
    focus and sponsorship to the test, which plays the manager."""
    team.manager = User.objects.create_user(
        email=f"{team.code.lower()}-manager@example.com", password="s0meth1ng-good",
    )
    team.save(update_fields=["manager"])
    return team


@pytest.fixture
def managed_team(db) -> Team:
    manager = User.objects.create_user(email="manager@example.com", password="s0meth1ng-good")
    return Team.objects.create(name="Team Beta", code="BET", manager=manager)


def _formula_at(rider: Rider, age: int) -> int:
    """`weekly_salary_for` priced against a copy of `rider` at another age.
    `weekly_salary_for` is pure and reads only speciality, age and the five
    engine attributes, so an unsaved copy answers "what would this rider
    have earned at this age" without touching the database."""
    clone = Rider(
        name=rider.name, speciality=rider.speciality, age=age,
        climb=rider.climb, sprint=rider.sprint, flat=rider.flat,
        resistance=rider.resistance, positioning=rider.positioning,
    )
    return weekly_salary_for(clone)


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


def make_scheduled_race(name: str, starts_at, course=None) -> Race:
    return Race.objects.create(
        name=name,
        course=course if course is not None else [{"length": 500.0, "gradient": 0.0}],
        starts_at=starts_at,
        status=Race.Status.SCHEDULED,
    )


def test_tick_with_nothing_scheduled_does_nothing(db, four_riders):
    run = tick()

    assert run.races_started == 0
    assert run.races_finished == 0
    assert run.capped is False


def test_tick_runs_a_due_race_once(db, four_riders):
    clock: MockClock = get_clock()
    race = make_scheduled_race("Due Race", now() + timedelta(hours=1))
    clock.advance_to_next_due()

    run = tick()

    race.refresh_from_db()
    assert race.status == Race.Status.FINISHED
    assert race.finished_at == now()
    assert run.races_started == 1
    assert run.races_finished == 1
    assert RaceResult.objects.filter(race=race).count() == len(four_riders)


def test_tick_is_capped_at_catch_up_max_races(db, four_riders):
    clock: MockClock = get_clock()
    GameClock.load()
    GameClock.objects.filter(pk=1).update(catch_up_max_races=2)
    due_at = now() + timedelta(hours=1)
    for i in range(4):
        make_scheduled_race(f"Race {i}", due_at)
    clock.set(due_at)

    run = tick()

    assert run.races_started == 2
    assert run.capped is True
    assert Race.objects.filter(status=Race.Status.SCHEDULED).count() == 2


def test_tick_clamps_the_claim_limit_when_reclaimed_alone_exceeds_the_cap(db, four_riders):
    # Reclaimed races count against the same cap as newly-claimed ones. If
    # reclaimed races alone already exceed the cap, the claim limit must
    # clamp to zero rather than going negative (a negative slice stop would
    # silently return an empty queryset either way, but the cap must still
    # report correctly and nothing must error).
    GameClock.load()
    GameClock.objects.filter(pk=1).update(catch_up_max_races=1)
    for i in range(2):
        Race.objects.create(
            name=f"Stranded {i}", course=[{"length": 500.0, "gradient": 0.0}],
            starts_at=now() - timedelta(hours=1), status=Race.Status.RUNNING,
        )

    run = tick()

    assert run.capped is True
    assert Race.objects.filter(status=Race.Status.RUNNING).count() == 0


def test_second_tick_does_not_rerun_a_finished_race(db, four_riders):
    clock: MockClock = get_clock()
    race = make_scheduled_race("Once Only", now() + timedelta(hours=1))
    clock.advance_to_next_due()

    tick()
    race.refresh_from_db()
    assert race.status == Race.Status.FINISHED
    first_count = RaceResult.objects.filter(race=race).count()

    tick()
    race.refresh_from_db()
    assert race.status == Race.Status.FINISHED
    assert RaceResult.objects.filter(race=race).count() == first_count


def test_interrupted_race_is_reclaimed(db, four_riders):
    race = Race.objects.create(
        name="Stranded",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=now() - timedelta(hours=1),
        status=Race.Status.RUNNING,
    )

    run = tick()

    race.refresh_from_db()
    assert race.status == Race.Status.FINISHED
    assert RaceResult.objects.filter(race=race).count() == len(four_riders)
    assert run.races_finished >= 1


def test_race_failure_marks_failed_and_continues(db, four_riders):
    clock: MockClock = get_clock()
    due_at = now() + timedelta(hours=1)
    bad = make_scheduled_race("Broken Course", due_at, course=[{"length": "oops"}])
    good = make_scheduled_race("Good Race", due_at)
    clock.set(due_at)

    tick()

    bad.refresh_from_db()
    good.refresh_from_db()
    assert bad.status == Race.Status.FAILED
    assert good.status == Race.Status.FINISHED
    assert RaceResult.objects.filter(race=good).count() == len(four_riders)


def test_tick_scores_finished_races(db, four_riders, team):
    clock: MockClock = get_clock()
    race = make_scheduled_race("Due Race", now() + timedelta(hours=1))
    clock.advance_to_next_due()

    tick()

    assert RacePoints.objects.filter(race=race, team=team).exists()


def test_a_race_that_fails_to_score_is_marked_failed(db, four_riders, monkeypatch):
    clock: MockClock = get_clock()
    due_at = now() + timedelta(hours=1)
    bad = make_scheduled_race("Bad At Scoring", due_at)
    good = make_scheduled_race("Good Race", due_at)
    clock.set(due_at)

    original_score_race = world_services.score_race

    def _raise_for_bad(race):
        if race.pk == bad.pk:
            raise RuntimeError("scoring exploded")
        return original_score_race(race)

    monkeypatch.setattr("world.services.score_race", _raise_for_bad)

    tick()

    bad.refresh_from_db()
    good.refresh_from_db()
    assert bad.status == Race.Status.FAILED
    assert good.status == Race.Status.FINISHED
    assert RacePoints.objects.filter(race=good).exists()


def test_tick_records_a_season_opening(db):
    clock: MockClock = get_clock()
    season = Season.objects.create(number=1, starts_at=now())
    clock.set(season.starts_at + timedelta(hours=1))

    run = tick()

    assert run.seasons_opened == 1
    assert run.seasons_closed == 0
    assert SeasonTransition.objects.filter(
        season=season, kind=SeasonTransition.Kind.OPENED,
    ).exists()


def test_tick_does_not_record_a_transition_twice(db):
    clock: MockClock = get_clock()
    season = Season.objects.create(number=1, starts_at=now())
    clock.set(season.starts_at + timedelta(hours=1))

    first = tick()
    second = tick()

    assert first.seasons_opened == 1
    assert second.seasons_opened == 0
    assert SeasonTransition.objects.filter(
        season=season, kind=SeasonTransition.Kind.OPENED,
    ).count() == 1


@pytest.fixture
def young_rider(db, team) -> Rider:
    return Rider.objects.create(
        name="Young Rider",
        team=team,
        speciality=Rider.Speciality.CLIMBER,
        age=20,
        peak_age=27,
        potential=90,
        decline_rate=50,
        climb=40,
        sprint=40,
        flat=40,
        resistance=40,
        positioning=40,
    )


def test_a_tick_applies_one_week_of_growth(db, young_rider):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    clock.set(week_one.starts_at + timedelta(hours=1))

    run = tick()
    young_rider.refresh_from_db()

    assert run.weeks_processed == 1
    # A young rider well below potential moves every week, even if the
    # movement is too small to cross a whole stored point yet.
    assert young_rider.climb > 40 or young_rider.growth_debt.get("climb", 0) > 0


def test_a_tick_three_weeks_late_applies_three_weeks_of_growth(db, young_rider):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_four = season.weeks.get(number=4)
    clock.set(week_four.starts_at + timedelta(hours=1))

    run = tick()

    assert run.weeks_processed == 4


def test_two_ticks_in_the_same_week_apply_growth_once(db, young_rider):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    clock.set(week_one.starts_at + timedelta(hours=1))

    tick()
    young_rider.refresh_from_db()
    after_first = (young_rider.climb, dict(young_rider.growth_debt))

    tick()
    young_rider.refresh_from_db()
    after_second = (young_rider.climb, dict(young_rider.growth_debt))

    assert after_first == after_second


def test_training_applies_once_per_week(db, team):
    # One week boundary crossed -> exactly one training pass -> one report
    # for the trainer's team, focused on what the manager chose.
    _give_a_manager(team)
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    Trainer.objects.create(
        name="Coach", team=team,
        climb=100, sprint=30, flat=30, resistance=30, positioning=30,
    )
    Rider.objects.create(
        name="Trainee", team=team, age=25, peak_age=27, potential=70,
        climb=89, sprint=40, flat=40, resistance=40, positioning=40,
    )
    set_focus(team, "climb")
    clock.set(week_one.starts_at + timedelta(hours=1))

    run = tick()

    report = TrainingWeekReport.objects.get(team=team)
    assert report.week == week_one
    assert report.attribute == "climb"
    # climb 89 (display 8) plus a focused week's points crosses display 9,
    # so the report records a visible change.
    assert report.changes
    assert run.riders_trained >= 1


def test_three_missed_weeks_apply_three_training_weeks(db, team):
    # The load-bearing test for Design decision 3: catching up three weeks
    # late must run one training pass PER week (each with its own focus and
    # races), not one collapsed pass for the whole gap. Collapsing back to
    # `apply_weekly_growth(weeks=len(weeks))` leaves exactly one report and
    # this test fails.
    _give_a_manager(team)
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_three = season.weeks.get(number=3)
    Trainer.objects.create(
        name="Coach", team=team,
        climb=100, sprint=30, flat=30, resistance=30, positioning=30,
    )
    Rider.objects.create(
        name="Trainee", team=team, age=25, peak_age=27, potential=70,
        climb=89, sprint=40, flat=40, resistance=40, positioning=40,
    )
    set_focus(team, "climb")
    clock.set(week_three.starts_at + timedelta(hours=1))

    run = tick()

    assert run.weeks_processed == 3
    reports = TrainingWeekReport.objects.filter(team=team).order_by("week__number")
    assert reports.count() == 3
    assert {report.attribute for report in reports} == {"climb"}
    assert run.riders_trained >= 1


def test_a_rider_whose_displayed_value_moves_gets_a_snapshot_for_that_week(db, team):
    _give_a_manager(team)
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    Trainer.objects.create(
        name="Coach", team=team,
        climb=100, sprint=30, flat=30, resistance=30, positioning=30,
    )
    trainee = Rider.objects.create(
        name="Trainee", team=team, age=25, peak_age=27, potential=70,
        climb=89, sprint=40, flat=40, resistance=40, positioning=40,
    )
    set_focus(team, "climb")
    clock.set(week_one.starts_at + timedelta(hours=1))
    RiderAttributeSnapshot.objects.filter(rider=trainee).delete()

    tick()

    snapshot = RiderAttributeSnapshot.objects.get(rider=trainee, week=week_one)
    # climb 89 (display 8) plus a focused week's points crosses display 9.
    assert snapshot.climb == 9


def test_a_rider_whose_displayed_value_does_not_move_gets_no_snapshot_that_week(db, team):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    # Well below potential and speciality ceiling, but the movement is far
    # too small to cross a display threshold in a single week.
    steady = Rider.objects.create(
        name="Steady", team=team, age=25, peak_age=27, potential=70,
        climb=40, sprint=40, flat=40, resistance=40, positioning=40,
    )
    clock.set(week_one.starts_at + timedelta(hours=1))
    RiderAttributeSnapshot.objects.filter(rider=steady).delete()

    tick()

    assert not RiderAttributeSnapshot.objects.filter(rider=steady, week=week_one).exists()


def test_a_late_tick_attributes_each_crossed_weeks_change_to_that_week(db, team):
    # D7: a tick that catches up several missed weeks must attribute each
    # week's crossing to that week, not bunch them into the week the tick
    # happened to run. Two riders, each set up to cross a display threshold
    # in a *different* one of the three missed weeks (one week of ~1.8
    # stored-point decline is not enough to cross a ten-point boundary more
    # than once, so this uses two riders rather than one rider crossing
    # three times).
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_three = season.weeks.get(number=3)
    # decline_rate 100, three years past peak_age (capped): ~1.8 stored
    # points/week. Starting one point above a ten-boundary crosses it in
    # week 1; starting deep in a band and needing ~1.9 points more crosses
    # in week 2.
    # sprint/flat/resistance/positioning sit mid-band (45, not a ten-boundary)
    # so only `climb` ever crosses a display threshold in either rider.
    week_one_faller = Rider.objects.create(
        name="Week One Faller", team=team, age=33, peak_age=27,
        potential=50, decline_rate=100,
        climb=90, sprint=45, flat=45, resistance=45, positioning=45,
    )
    week_two_faller = Rider.objects.create(
        name="Week Two Faller", team=team, age=33, peak_age=27,
        potential=50, decline_rate=100,
        climb=81, sprint=45, flat=45, resistance=45, positioning=45,
    )
    clock.set(week_three.starts_at + timedelta(hours=1))
    RiderAttributeSnapshot.objects.filter(rider__in=[week_one_faller, week_two_faller]).delete()

    tick()

    one_weeks = set(
        RiderAttributeSnapshot.objects.filter(rider=week_one_faller)
        .values_list("week__number", flat=True)
    )
    two_weeks = set(
        RiderAttributeSnapshot.objects.filter(rider=week_two_faller)
        .values_list("week__number", flat=True)
    )
    assert one_weeks == {1}
    assert two_weeks == {2}


def test_rider_on_teamless_squad_still_gains_from_racing(db, team):
    # No trainer anywhere: the trainer half of training is off, but the
    # race-based half still applies. The race runs during week 1; entering
    # week 2 is the rollover that rewards week 1's racing. `flat` sits at or
    # above its ceiling for this climber, so its only possible movement is
    # the RACE_TRAINING_UNIT stored points from a 150 km flat race.
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    week_two = season.weeks.get(number=2)
    rider = Rider.objects.create(
        name="Racer", team=team,
        speciality=Rider.Speciality.CLIMBER,
        age=25, peak_age=27, potential=70,
        climb=60, sprint=60, flat=60, resistance=60, positioning=60,
    )
    for i in range(3):
        Rider.objects.create(
            name=f"Teammate {i}", team=team,
            speciality=Rider.Speciality.CLIMBER,
            age=25, peak_age=27, potential=70,
            climb=60, sprint=60, flat=60, resistance=60, positioning=60,
        )
    Race.objects.create(
        name="Week One Race",
        course=[{"length": 150_000.0, "gradient": 0.0}],
        starts_at=week_one.starts_at + timedelta(hours=1),
        week=week_one,
        status=Race.Status.SCHEDULED,
    )

    clock.set(week_one.starts_at + timedelta(hours=1))
    first = tick()                       # week 1 opens; its race runs
    clock.set(week_two.starts_at + timedelta(hours=1))
    tick()                               # week 2 opens: week 1's racing is rewarded
    rider.refresh_from_db()

    assert first.races_finished == 1
    assert rider.growth_debt.get("flat", 0) == pytest.approx(0.25)
    # No team has a trainer, so no TrainingWeekReport is written at all.
    assert not TrainingWeekReport.objects.exists()


def test_concurrent_ticks_train_once(db, team):
    _give_a_manager(team)
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    Trainer.objects.create(
        name="Coach", team=team,
        climb=100, sprint=30, flat=30, resistance=30, positioning=30,
    )
    Rider.objects.create(
        name="Trainee", team=team, age=25, peak_age=27, potential=70,
        climb=89, sprint=40, flat=40, resistance=40, positioning=40,
    )
    set_focus(team, "climb")
    clock.set(week_one.starts_at + timedelta(hours=1))

    first = tick()
    second = tick()

    assert first.riders_trained >= 1
    assert second.riders_trained == 0
    assert TrainingWeekReport.objects.filter(team=team).count() == 1


def test_riders_age_when_a_season_closes(db, young_rider):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    clock.set(season.ends_at + timedelta(hours=1))

    run = tick()
    young_rider.refresh_from_db()

    assert run.riders_aged == 1
    assert young_rider.age == 21


def test_riders_do_not_age_mid_season(db, young_rider):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    clock.set(week_one.starts_at + timedelta(hours=1))

    run = tick()
    young_rider.refresh_from_db()

    assert run.riders_aged == 0
    assert young_rider.age == 20


def _veteran(name: str, *, age: int, team, **overrides) -> Rider:
    """A rider whose traits put their retirement age at the very top of the
    window (38), so `age` alone decides whether they are due."""
    defaults = dict(
        speciality=Rider.Speciality.CLIMBER,
        peak_age=32,
        decline_rate=1,
        climb=40, sprint=40, flat=40, resistance=40, positioning=40,
    )
    defaults.update(overrides)
    return Rider.objects.create(name=name, team=team, age=age, **defaults)


def test_tick_retires_due_riders_at_season_close(db, team):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    rider = _veteran("Due", age=38, team=team)
    clock.set(season.ends_at + timedelta(hours=1))

    run = tick()
    rider.refresh_from_db()

    assert run.riders_retired == 1
    assert rider.retired_at is not None
    assert rider.team is None


def test_tick_does_not_retire_mid_season(db, team):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    rider = _veteran("Marked", age=38, team=team)
    week_one = season.weeks.get(number=1)
    clock.set(week_one.starts_at + timedelta(hours=1))

    run = tick()
    rider.refresh_from_db()

    assert run.riders_retired == 0
    assert rider.retired_at is None
    assert rider.team == team


def test_tick_retires_before_ageing(db, team):
    """Load-bearing ordering (plan D4): a rider must carry the warning for a
    full season. Ageing first would take a rider from one year below their
    retirement age into it and retire them in the same tick, with no season
    ever having flagged them."""
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    not_yet = _veteran("Not Yet", age=37, team=team)
    due = _veteran("Due", age=38, team=team)
    clock.set(season.ends_at + timedelta(hours=1))

    tick()
    not_yet.refresh_from_db()
    due.refresh_from_db()

    assert not_yet.retired_at is None
    assert not_yet.age == 38
    assert due.retired_at is not None
    assert due.age == 38


def test_retired_rider_is_stamped_with_final_week_start(db, team):
    """The stamp is the closing season's last week, not its ends_at — the
    latter falls outside the season and would resolve to the next season's
    week 1 in the profile's retired label."""
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    final_week = season.weeks.get(number=SEASON_WEEKS)
    rider = _veteran("Due", age=38, team=team)
    clock.set(season.ends_at + timedelta(hours=1))

    tick()
    rider.refresh_from_db()

    assert rider.retired_at == final_week.starts_at


def test_a_season_close_retirement_is_a_departure_dated_to_the_final_week(db, team):
    """#158: the manager comes back to a shorter roster, and this is the
    record that says why — at the age the rider last showed, since retiring
    runs before ageing."""
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    final_week = season.weeks.get(number=SEASON_WEEKS)
    rider = _veteran("Due", age=38, team=team)
    clock.set(season.ends_at + timedelta(hours=1))

    tick()

    departure = Departure.objects.get(team=team)
    assert (departure.rider_id, departure.kind, departure.at, departure.age) == (
        rider.pk, Departure.Kind.RETIRED, final_week.starts_at, 38,
    )


def test_retired_rider_leaves_salary_review(db, managed_team):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    retiree = _veteran("Retiree", age=38, team=managed_team, weekly_salary=1000)
    survivor = Rider.objects.create(
        name="Survivor", team=managed_team, speciality=Rider.Speciality.CLIMBER,
        age=25, peak_age=22, decline_rate=1, weekly_salary=1000,
        climb=40, sprint=40, flat=40, resistance=40, positioning=40,
    )
    original_salary = retiree.weekly_salary
    clock.set(season.ends_at + timedelta(hours=1))

    tick()
    retiree.refresh_from_db()

    report = SalaryReviewReport.objects.get(team=managed_team)
    assert retiree.retired_at is not None
    assert retiree.weekly_salary == original_salary
    assert all(change["rider_id"] != retiree.pk for change in report.changes)
    assert any(change["rider_id"] == survivor.pk for change in report.changes)


def test_tick_records_riders_retired(db, team):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    for i in range(3):
        _veteran(f"Due {i}", age=38, team=team)
    _veteran("Not Yet", age=37, team=team)
    clock.set(season.ends_at + timedelta(hours=1))

    run = tick()

    assert run.riders_retired == 3
    assert run.agents_retired == 0  # age-driven, not free-agent expiry


def test_an_intake_week_adds_free_agents_and_counts_them(db):
    from riders.free_agent_intake import FREE_AGENT_INTAKE_SIZE
    from transfers.services import free_agents

    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_two = season.weeks.get(number=2)
    clock.set(week_two.starts_at + timedelta(hours=1))

    run = tick()

    # Weeks 1 and 2 are crossed; only week 2 is an intake week.
    assert run.free_agents_generated == FREE_AGENT_INTAKE_SIZE
    assert free_agents().filter(unattached_since=week_two.starts_at).count() == FREE_AGENT_INTAKE_SIZE


def test_a_short_unmanaged_team_signs_a_free_agent_at_the_next_boundary(db, team):
    """#157 end to end: the intake fills the pool, and a week later the AI
    team that retirement left short signs from it."""
    from economy.services import ensure_opening_balance

    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    ensure_opening_balance(team, at=now())
    for i in range(ROSTER_SIZE - 1):
        _veteran(f"Stays {i}", age=25, team=team)
    clock.set(season.weeks.get(number=2).starts_at + timedelta(hours=1))
    first = tick()
    clock.set(season.weeks.get(number=3).starts_at + timedelta(hours=1))

    second = tick()

    assert first.ai_free_agents_signed == 0  # the intake is a week old first
    assert second.ai_free_agents_signed == 1
    assert team.riders.count() == ROSTER_SIZE


def test_tick_reprices_riders_at_season_close(db, team):
    # A rider stored well below their formula price is brought up to it when
    # the season closes — a period end makes the stored wage honest again.
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    rider = Rider.objects.create(
        name="Underpaid", team=team, speciality=Rider.Speciality.CLIMBER,
        age=24, peak_age=22, decline_rate=1,
        climb=40, sprint=40, flat=40, resistance=40, positioning=40,
        weekly_salary=1000,
    )
    clock.set(season.ends_at + timedelta(hours=1))

    run = tick()
    rider.refresh_from_db()

    assert run.seasons_closed == 1
    assert rider.age == 25
    assert rider.weekly_salary == weekly_salary_for(rider)
    assert rider.weekly_salary > 1000
    assert run.riders_repriced == 1


def test_tick_reprices_after_ageing(db, team):
    # Load-bearing ordering (spec, *Ordering at the boundary*): next season's
    # wage must be priced against the rider AFTER ageing. Repricing before
    # ageing would price the 32-year-old. decline_rate=1 pins the attributes,
    # so the year-on-year movement comes only from the age band dipping below
    # the prime cutoff — isolating the ordering from ordinary growth.
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    rider = Rider.objects.create(
        name="Ageing Out", team=team, speciality=Rider.Speciality.CLIMBER,
        age=32, peak_age=27, decline_rate=1,
        climb=80, sprint=80, flat=80, resistance=80, positioning=80,
    )
    clock.set(season.ends_at + timedelta(hours=1))

    run = tick()
    rider.refresh_from_db()

    assert run.riders_aged == 1
    assert rider.age == 33
    assert _formula_at(rider, 33) != _formula_at(rider, 32)
    assert rider.weekly_salary == _formula_at(rider, 33)
    assert run.riders_repriced == 1


def test_tick_does_not_reprice_at_a_week_boundary(db, team):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    rider = Rider.objects.create(
        name="Mid Season", team=team, speciality=Rider.Speciality.CLIMBER,
        age=25, peak_age=22, decline_rate=1,
        climb=40, sprint=40, flat=40, resistance=40, positioning=40,
        weekly_salary=2000,
    )
    clock.set(week_one.starts_at + timedelta(hours=1))

    run = tick()
    rider.refresh_from_db()

    assert run.seasons_closed == 0
    assert run.riders_repriced == 0
    assert rider.weekly_salary == 2000


def test_tick_writes_a_salary_review_per_managed_team(db, team, managed_team):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    rider = Rider.objects.create(
        name="Reported", team=managed_team, speciality=Rider.Speciality.CLIMBER,
        age=25, peak_age=22, decline_rate=1,
        climb=40, sprint=40, flat=40, resistance=40, positioning=40,
        weekly_salary=1000,
    )
    clock.set(season.ends_at + timedelta(hours=1))

    run = tick()
    rider.refresh_from_db()

    report = SalaryReviewReport.objects.get(team=managed_team)
    assert run.salary_reviews == 1
    assert report.season == season
    assert report.payroll_before == 1000
    assert report.payroll_after == rider.weekly_salary
    assert report.changes == [{
        "rider_id": rider.pk, "rider_name": "Reported",
        "from": 1000, "to": rider.weekly_salary,
    }]
    assert SalaryReviewReport.objects.count() == 1
    assert not SalaryReviewReport.objects.filter(team=team).exists()


def test_tick_reprices_once_per_closed_season(db, managed_team):
    # A tick catching up two closed seasons applies the boundary twice: two
    # repricings and one report per season per managed team. The rider leaves
    # the prime band at the second close (32 -> 33), so each close moves the
    # stored price — the reports must be keyed to their own season, not one
    # report clobbering the other.
    clock: MockClock = get_clock()
    season_one = make_season_with_weeks(1, now())
    season_two = make_season_with_weeks(2, season_one.ends_at)
    rider = Rider.objects.create(
        name="Twice Priced", team=managed_team, speciality=Rider.Speciality.CLIMBER,
        age=31, peak_age=27, decline_rate=1,
        climb=80, sprint=80, flat=80, resistance=80, positioning=80,
    )
    clock.set(season_two.ends_at + timedelta(hours=1))

    run = tick()
    rider.refresh_from_db()

    reports = list(SalaryReviewReport.objects.filter(team=managed_team).order_by("season__starts_at"))
    assert run.seasons_closed == 2
    assert run.riders_repriced == 2
    assert run.salary_reviews == 2
    assert rider.age == 33
    assert rider.weekly_salary == _formula_at(rider, 33)
    assert len(reports) == 2
    assert [report.season for report in reports] == [season_one, season_two]
    # First close brought the 32-year-old's stored wage to the formula.
    assert reports[0].payroll_before == 1200
    assert reports[0].payroll_after == _formula_at(rider, 32)
    # Second close moved it on to the 33-year-old's formula, on top of the
    # first close's stored value — not off the original one.
    assert reports[1].payroll_before == reports[0].payroll_after
    assert reports[1].payroll_after == rider.weekly_salary


def test_growth_is_applied_before_races_are_simulated(db, young_rider, team, monkeypatch):
    # A rider racing in the same tick their week's growth lands should
    # race with that week's attributes already applied. weeks_processed
    # and races_finished both being non-zero proves nothing about *order*
    # (either call order would produce the same counts), so this records
    # the actual call order and asserts growth happened first.
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    for i in range(3):
        Rider.objects.create(
            name=f"Teammate {i}", team=team,
            climb=60, sprint=60, flat=60, resistance=60, positioning=60,
        )
    Race.objects.create(
        name="Week One Race",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=week_one.starts_at + timedelta(hours=1),
        status=Race.Status.SCHEDULED,
    )
    clock.set(week_one.starts_at + timedelta(hours=1))

    call_order: list[str] = []
    original_apply_weekly_growth = world_services.apply_weekly_growth
    original_simulate_race = world_services.simulate_race

    def _record_growth(*args, **kwargs):
        call_order.append("growth")
        return original_apply_weekly_growth(*args, **kwargs)

    def _record_race(*args, **kwargs):
        call_order.append("race")
        return original_simulate_race(*args, **kwargs)

    monkeypatch.setattr("world.services.apply_weekly_growth", _record_growth)
    monkeypatch.setattr("world.services.simulate_race", _record_race)

    run = tick()

    assert run.weeks_processed == 1
    assert run.races_finished == 1
    assert call_order == ["growth", "race"]


def test_tick_tops_up_the_pool_when_a_season_opens(db):
    clock: MockClock = get_clock()
    season = Season.objects.create(number=1, starts_at=now())
    clock.set(season.starts_at + timedelta(hours=1))
    before_count = Trainer.objects.count()

    tick()

    assert Trainer.objects.count() == before_count + TRAINERS_PER_SEASON_BOUNDARY


def test_a_second_tick_does_not_top_up_again(db):
    clock: MockClock = get_clock()
    season = Season.objects.create(number=1, starts_at=now())
    clock.set(season.starts_at + timedelta(hours=1))
    before_count = Trainer.objects.count()

    tick()
    tick()

    assert Trainer.objects.count() == before_count + TRAINERS_PER_SEASON_BOUNDARY


def test_tick_with_no_boundary_crossed_does_not_top_up(db, four_riders):
    before_count = Trainer.objects.count()

    tick()

    assert Trainer.objects.count() == before_count


def test_tick_recovers_freshness_for_resting_riders(db, team):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    rider = Rider.objects.create(
        name="Rested", team=team,
        climb=60, sprint=60, flat=60, resistance=60, positioning=60,
        freshness=50, recovery_rate=100,
    )
    clock.set(week_one.starts_at + timedelta(hours=1))

    run = tick()
    rider.refresh_from_db()

    assert run.weeks_processed == 1
    assert rider.freshness == 70  # recovery_rate 100 -> RECOVERY_MAX (20)


def test_tick_does_not_recover_a_rider_who_raced_that_week(db, team):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    week_two = season.weeks.get(number=2)
    racer = Rider.objects.create(
        name="Racer", team=team,
        climb=60, sprint=60, flat=60, resistance=60, positioning=60,
    )
    for i in range(3):
        Rider.objects.create(
            name=f"Teammate {i}", team=team,
            climb=60, sprint=60, flat=60, resistance=60, positioning=60,
        )
    rester = Rider.objects.create(
        name="Rester", team=None,
        climb=60, sprint=60, flat=60, resistance=60, positioning=60,
        recovery_rate=100,
    )
    Race.objects.create(
        name="Week One Race",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=week_one.starts_at + timedelta(days=1),
        week=week_one,
        status=Race.Status.SCHEDULED,
    )

    clock.advance_to_next_due()
    tick()                            # week 1 opens; its race runs
    racer.refresh_from_db()
    assert racer.freshness == 75      # paid the race cost

    rester.freshness = 50
    rester.save(update_fields=["freshness"])
    clock.set(week_two.starts_at + timedelta(hours=1))
    tick()                            # week 2 opens: week 1's racers skip recovery
    racer.refresh_from_db()
    rester.refresh_from_db()

    assert racer.freshness == 75      # raced the week being settled -> no recovery
    assert rester.freshness == 70     # rested -> +20


def test_tick_does_not_recover_a_rider_who_did_not_finish(db, team):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    week_two = season.weeks.get(number=2)
    cut = Rider.objects.create(
        name="Cut", team=team,
        climb=60, sprint=60, flat=60, resistance=60, positioning=60,
    )
    rester = Rider.objects.create(
        name="Rester", team=None,
        climb=60, sprint=60, flat=60, resistance=60, positioning=60,
        recovery_rate=100,
    )
    race = Race.objects.create(
        name="Week One Race",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=week_one.starts_at + timedelta(days=1),
        week=week_one,
        status=Race.Status.FINISHED,
    )
    RaceResult.objects.create(race=race, rider=cut, position=1, finish_time=None)

    clock.advance_to_next_due()
    tick()                            # week 1 opens; no preceding week to settle

    # Week 1 has already run its (stubbed, unfinished) race, but the cost of
    # that isn't this test's concern (see
    # racing/tests.py::test_simulate_race_deducts_freshness_from_non_finishers)
    # — set it directly, same as the source test does for `rester`.
    cut.freshness = 75
    cut.save(update_fields=["freshness"])
    rester.freshness = 50
    rester.save(update_fields=["freshness"])
    clock.set(week_two.starts_at + timedelta(hours=1))
    tick()                            # week 2 opens: week 1's starters skip recovery
    cut.refresh_from_db()
    rester.refresh_from_db()

    assert cut.freshness == 75        # started the week being settled -> no recovery
    assert rester.freshness == 70     # rested -> +20


def test_three_missed_weeks_recover_three_times(db, team, monkeypatch):
    # One recovery pass per week boundary, not one collapsed pass for the
    # whole gap. A purely resting rider is numerically identical either way
    # (linear recovery, well under the ceiling), so the per-week loop is
    # proven by counting calls — the same shape of proof as
    # test_three_missed_weeks_apply_three_training_weeks' report count.
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_three = season.weeks.get(number=3)
    rider = Rider.objects.create(
        name="Rested", team=team,
        climb=1, sprint=1, flat=1, resistance=1, positioning=1,
        freshness=30, recovery_rate=50,
    )

    calls: list[set[int]] = []
    original = world_services.apply_weekly_recovery

    def _counted(**kwargs):
        calls.append(set(kwargs["exclude_ids"]))
        return original(**kwargs)

    monkeypatch.setattr("world.services.apply_weekly_recovery", _counted)
    clock.set(week_three.starts_at + timedelta(hours=1))

    run = tick()

    assert run.weeks_processed == 3
    assert len(calls) == 3
    rider.refresh_from_db()
    assert rider.freshness == 30 + 3 * 14  # recovery_rate 50 -> ~14/week


# --- The field's level at season close (#166) -------------------------------

def test_field_change_percent_reads_as_the_field_getting_stronger():
    # The factor falls as the field strengthens: 1.0 -> 0.943 is ~6% stronger.
    assert world_services.field_change_percent(1.0, 1.0 / 1.06) == 6
    assert world_services.field_change_percent(1.0, 1.0 / 0.97) == -3
    assert world_services.field_change_percent(0.9, 0.9) == 0


def test_season_close_prices_against_the_field_and_says_so(db, team, managed_team):
    from riders.models import FieldLevel
    from riders.services import FIELD_MIN_RIDERS

    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    for i in range(FIELD_MIN_RIDERS):
        Rider.objects.create(
            name=f"Strong {i}", team=managed_team if i % 2 else team,
            speciality=Rider.Speciality.ROULEUR, age=27, peak_age=27, decline_rate=1,
            climb=60, sprint=60, flat=60, resistance=60, positioning=60,
            weekly_salary=1000,
        )
    clock.set(season.ends_at + timedelta(hours=1))

    tick()

    factor = FieldLevel.objects.get().factor
    report = SalaryReviewReport.objects.get(team=managed_team)
    assert factor < 1.0
    assert report.field_change_percent == world_services.field_change_percent(1.0, factor)
    assert report.field_change_percent > 0
