from __future__ import annotations

from datetime import timedelta

import pytest

from accounts.models import User
from competitions.models import MarkerPoints
from economy.models import (
    MERCHANDISE_FANBASE_PER_CREDIT,
    STARTING_FANBASE,
    WEEKLY_FANBASE_DECAY,
    FanbaseEntry,
    LedgerEntry,
    SponsorOffer,
)
from economy.services import active_contract, ensure_opening_balance, sign_offer
from competitions.models import RacePoints
from racing.models import Race, RaceMarker, RaceResult, RaceSquad, RaceSquadRider, StageRace
from racing.services import simulate_race as _real_simulate_race
from riders.development_squad import change_level
from riders.models import ENGINE_ATTRIBUTES, DevelopmentSquad, Rider
from staff.services import set_focus
from schedule.models import SEASON_WEEKS, Season, Week
from staff.models import Trainer, TrainingWeekReport
from staff.pricing import weekly_salary
from teams.models import Team
from transfers.models import Auction
from transfers.services import list_for_auction
from world.ai_management import focus_for_week
from world.ai_market import AI_LISTING_EVERY_WEEKS
from world.clocks import MockClock
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
def riders(db, team) -> list[Rider]:
    # Distinct weekly_salary per rider (#25) so a wage assertion that summed
    # a head count times a flat rate, rather than the riders' actual
    # salaries, would be caught rather than passing by coincidence.
    return [
        Rider.objects.create(
            name=f"Rider {i}",
            team=team,
            climb=60, sprint=60, flat=60, resistance=60, positioning=60,
            weekly_salary=1000 + i * 250,
        )
        for i in range(4)
    ]


def give_starting_fanbase(team, at):
    FanbaseEntry.objects.create(
        team=team, kind=FanbaseEntry.Kind.STARTING, delta=STARTING_FANBASE,
        occurred_at=at, description="Starting fanbase",
    )


def test_tick_charges_wages_for_the_week_it_crosses(db, team, riders):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    clock.set(week_one.starts_at + timedelta(hours=1))

    run = tick()

    assert run.wage_entries == 1
    entry = LedgerEntry.objects.get(team=team, kind=LedgerEntry.Kind.WAGES)
    assert entry.week == week_one
    assert entry.occurred_at == week_one.starts_at
    assert entry.amount == -sum(rider.weekly_salary for rider in riders)


def test_catch_up_charges_each_missed_week_separately(db, team, riders):
    # The load-bearing test for Design decision 3 (applied to wages): a
    # three-week jump must produce three separate wage entries dated to
    # three different weeks, never one lump sum and never skipped weeks.
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_three = season.weeks.get(number=3)
    clock.set(week_three.starts_at + timedelta(hours=1))

    run = tick()

    assert run.weeks_processed == 3
    assert run.wage_entries == 3
    entries = LedgerEntry.objects.filter(team=team, kind=LedgerEntry.Kind.WAGES).order_by("week__number")
    assert entries.count() == 3
    assert set(entries.values_list("week_id", flat=True)) == {
        season.weeks.get(number=n).pk for n in (1, 2, 3)
    }
    assert set(entries.values_list("week__starts_at", flat=True)) == {
        season.weeks.get(number=n).starts_at for n in (1, 2, 3)
    }


def test_running_tick_twice_does_not_double_charge(db, team, riders):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_two = season.weeks.get(number=2)
    clock.set(week_two.starts_at + timedelta(hours=1))

    first = tick()
    # Moving the clock on to a fresh week is the reason a second tick runs
    # at all; only the *new* week may be charged.
    clock.set(season.weeks.get(number=3).starts_at + timedelta(hours=1))
    second = tick()

    assert first.wage_entries == 2
    assert second.wage_entries == 1
    assert LedgerEntry.objects.filter(team=team, kind=LedgerEntry.Kind.WAGES).count() == 3


def test_tick_with_no_boundary_crossed_charges_nothing(db, team, riders):
    run = tick()

    assert run.wage_entries == 0
    assert not LedgerEntry.objects.filter(kind=LedgerEntry.Kind.WAGES).exists()


def test_tick_pays_prize_money_for_a_finished_race(db, team, riders):
    clock: MockClock = get_clock()
    race = Race.objects.create(
        name="Due Race",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=now() + timedelta(hours=1),
        status=Race.Status.SCHEDULED,
    )
    clock.advance_to_next_due()

    run = tick()

    race.refresh_from_db()
    assert race.status == Race.Status.FINISHED
    placed = list(
        RaceResult.objects.filter(race=race, finish_time__isnull=False)
        .values_list("position", flat=True)
    )
    assert placed
    assert run.prize_entries == len(placed)
    entries = list(
        LedgerEntry.objects.filter(team=team, kind=LedgerEntry.Kind.PRIZE_MONEY)
        .order_by("position")
    )
    assert len(entries) == len(placed)
    assert [e.position for e in entries] == sorted(placed)
    assert all(e.race_id == race.pk for e in entries)
    assert all(e.amount > 0 for e in entries)
    assert all(e.occurred_at == race.finished_at for e in entries)
    assert all(e.description == f"Prize money — {race.name}" for e in entries)


def test_prize_failure_does_not_fail_the_race(db, team, riders, monkeypatch):
    clock: MockClock = get_clock()
    race = Race.objects.create(
        name="Due Race",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=now() + timedelta(hours=1),
        status=Race.Status.SCHEDULED,
    )
    clock.advance_to_next_due()

    def _raise(race):
        raise RuntimeError("prizes exploded")

    monkeypatch.setattr("world.services.prizes_by_team", _raise)

    run = tick()

    race.refresh_from_db()
    assert race.status == Race.Status.FINISHED
    assert run.races_finished == 1
    assert run.prize_entries == 0
    assert "prizes exploded" in run.error


def make_stage_race(team, riders, *, week, stage_count: int) -> StageRace:
    """A stage race with `stage_count` SCHEDULED stages on consecutive
    days of `week`, with `team`'s squad chosen once, for stage 1 — the
    shape ensure_squads carries forward to every later stage."""
    stage_race = StageRace.objects.create(name="Alpine Tour", week=week)
    stages = []
    for n in range(1, stage_count + 1):
        stage = Race.objects.create(
            name=f"Alpine Tour — Stage {n}",
            course=[{"length": 500.0, "gradient": 0.0}],
            starts_at=week.starts_at + timedelta(days=n - 1, hours=1),
            week=week,
            stage_race=stage_race,
            stage_number=n,
            status=Race.Status.SCHEDULED,
        )
        stages.append(stage)
    squad = RaceSquad.objects.create(race=stages[0], team=team)
    RaceSquadRider.objects.bulk_create([
        RaceSquadRider(squad=squad, rider=r, is_leader=(i == 0))
        for i, r in enumerate(riders)
    ])
    return stage_race


def test_tick_runs_stage_race_and_settles_gc(db, team, riders):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week = season.weeks.get(number=1)
    stage_race = make_stage_race(team, riders, week=week, stage_count=3)
    last_stage = stage_race.stages.get(stage_number=3)
    clock.set(last_stage.starts_at + timedelta(hours=1))

    tick()

    assert stage_race.stages.filter(status=Race.Status.FINISHED).count() == 3
    # Only one team raced, so GC points (best rider per team) award it a
    # single row, but GC prize money (every placed rider) can pay the same
    # team more than once — its other three riders placed too.
    gc_points = RacePoints.objects.filter(race=last_stage, kind=RacePoints.Kind.GC)
    assert gc_points.count() == 1
    assert gc_points.first().team_id == team.pk
    gc_prizes = LedgerEntry.objects.filter(
        team=team, race=last_stage, kind=LedgerEntry.Kind.GC_PRIZE_MONEY,
    )
    assert gc_prizes.exists()
    assert all(row.amount > 0 for row in gc_prizes)

    # Stage points/prizes still exist on every stage, unaffected by the GC.
    for stage in stage_race.stages.all():
        assert RacePoints.objects.filter(race=stage, kind=RacePoints.Kind.RACE).exists()


def test_catch_up_tick_runs_all_stages_in_order(db, team, riders):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week = season.weeks.get(number=1)
    stage_race = make_stage_race(team, riders, week=week, stage_count=3)
    last_stage = stage_race.stages.get(stage_number=3)
    # Jump straight past every stage in one move — a single tick must claim
    # and simulate all three, in order, in one call.
    clock.set(last_stage.starts_at + timedelta(hours=1))

    run = tick()

    assert run.races_finished == 3
    for stage in stage_race.stages.order_by("stage_number"):
        assert stage.status == Race.Status.FINISHED
        squad = RaceSquad.objects.get(race=stage, team=team)
        assert set(squad.members.values_list("rider_id", flat=True)) == {r.pk for r in riders}
    gc_rows = RacePoints.objects.filter(race=last_stage, kind=RacePoints.Kind.GC)
    assert gc_rows.count() == 1


def test_failed_final_stage_still_settles_gc(db, team, riders, monkeypatch):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week = season.weeks.get(number=1)
    stage_race = make_stage_race(team, riders, week=week, stage_count=2)
    last_stage = stage_race.stages.get(stage_number=2)
    clock.set(last_stage.starts_at + timedelta(hours=1))

    def _fail_last_stage(race, *, game_time):
        if race.stage_number == 2:
            raise RuntimeError("engine blew up")
        return _real_simulate_race(race, game_time=game_time)

    monkeypatch.setattr("world.services.simulate_race", _fail_last_stage)

    tick()

    last_stage.refresh_from_db()
    assert last_stage.status == Race.Status.FAILED
    # is_complete() only needs every stage FINISHED or FAILED, with at
    # least one FINISHED — stage 1 ran fine, so the GC still settles over it.
    gc_rows = RacePoints.objects.filter(race=last_stage, kind=RacePoints.Kind.GC)
    assert gc_rows.count() == 1


def test_gc_not_settled_until_last_stage(db, team, riders):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week = season.weeks.get(number=1)
    stage_race = make_stage_race(team, riders, week=week, stage_count=3)
    stage1 = stage_race.stages.get(stage_number=1)
    clock.set(stage1.starts_at + timedelta(hours=1))

    tick()

    stage1.refresh_from_db()
    assert stage1.status == Race.Status.FINISHED
    assert RacePoints.objects.filter(kind=RacePoints.Kind.GC).count() == 0


def test_tick_scores_sprint_points_for_a_finished_race(db, team, riders):
    clock: MockClock = get_clock()
    race = Race.objects.create(
        name="Due Race",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=now() + timedelta(hours=1),
        status=Race.Status.SCHEDULED,
    )
    RaceMarker.objects.create(
        race=race, kind=RaceMarker.Kind.SPRINT, name="Mid-line", distance=250.0,
        weight=RaceMarker.Weight.STANDARD,
    )
    clock.advance_to_next_due()

    tick()

    race.refresh_from_db()
    assert race.status == Race.Status.FINISHED
    assert MarkerPoints.objects.filter(marker__race=race).exists()


def test_sprint_scoring_failure_does_not_fail_the_race(db, team, riders, monkeypatch):
    clock: MockClock = get_clock()
    race = Race.objects.create(
        name="Due Race",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=now() + timedelta(hours=1),
        status=Race.Status.SCHEDULED,
    )
    RaceMarker.objects.create(
        race=race, kind=RaceMarker.Kind.SPRINT, name="Mid-line", distance=250.0,
    )
    clock.advance_to_next_due()

    def _raise(race):
        raise RuntimeError("sprint scoring exploded")

    monkeypatch.setattr("world.services.score_sprints", _raise)

    run = tick()

    race.refresh_from_db()
    assert race.status == Race.Status.FINISHED
    assert run.races_finished == 1
    assert not MarkerPoints.objects.filter(marker__race=race).exists()
    placed = list(
        RaceResult.objects.filter(race=race, finish_time__isnull=False)
        .values_list("position", flat=True)
    )
    assert run.prize_entries == len(placed)
    assert "sprint scoring exploded" in run.error


def test_tick_scores_mountain_points_for_a_finished_race(db, team, riders):
    clock: MockClock = get_clock()
    race = Race.objects.create(
        name="Due Race",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=now() + timedelta(hours=1),
        status=Race.Status.SCHEDULED,
    )
    RaceMarker.objects.create(
        race=race, kind=RaceMarker.Kind.MOUNTAIN, name="Final Top", distance=500.0,
        category=RaceMarker.Category.HC,
    )
    clock.advance_to_next_due()

    tick()

    race.refresh_from_db()
    assert race.status == Race.Status.FINISHED
    assert MarkerPoints.objects.filter(marker__race=race).exists()


def test_mountain_scoring_failure_does_not_fail_the_race(db, team, riders, monkeypatch):
    clock: MockClock = get_clock()
    race = Race.objects.create(
        name="Due Race",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=now() + timedelta(hours=1),
        status=Race.Status.SCHEDULED,
    )
    RaceMarker.objects.create(
        race=race, kind=RaceMarker.Kind.MOUNTAIN, name="Final Top", distance=500.0,
    )
    RaceMarker.objects.create(
        race=race, kind=RaceMarker.Kind.SPRINT, name="Mid-line", distance=250.0,
    )
    clock.advance_to_next_due()

    def _raise(race):
        raise RuntimeError("mountain scoring exploded")

    monkeypatch.setattr("world.services.score_mountains", _raise)

    run = tick()

    race.refresh_from_db()
    assert race.status == Race.Status.FINISHED
    assert run.races_finished == 1
    assert not MarkerPoints.objects.filter(
        marker__race=race, marker__kind=RaceMarker.Kind.MOUNTAIN,
    ).exists()
    assert MarkerPoints.objects.filter(
        marker__race=race, marker__kind=RaceMarker.Kind.SPRINT,
    ).exists()
    placed = list(
        RaceResult.objects.filter(race=race, finish_time__isnull=False)
        .values_list("position", flat=True)
    )
    assert run.prize_entries == len(placed)
    assert "mountain scoring exploded" in run.error


def make_trainer(team, **overrides):
    defaults = dict(
        name="Coach One", climb=90, sprint=40, flat=45, resistance=50, positioning=35,
    )
    defaults.update(overrides)
    return Trainer.objects.create(team=team, **defaults)


def test_tick_charges_trainer_salary(db, team, riders):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    trainer = make_trainer(team)
    clock.set(week_one.starts_at + timedelta(hours=1))

    run = tick()

    assert run.trainer_salary_entries == 1
    entry = LedgerEntry.objects.get(team=team, kind=LedgerEntry.Kind.TRAINER_SALARY)
    assert entry.week == week_one
    assert entry.occurred_at == week_one.starts_at
    assert entry.amount == -weekly_salary(trainer)


def test_catch_up_charges_each_week_once(db, team, riders):
    # The load-bearing test for Design decision 3: a three-week jump must
    # produce three separate salary entries dated to three different weeks,
    # never one lump sum and never skipped weeks.
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_three = season.weeks.get(number=3)
    make_trainer(team)
    clock.set(week_three.starts_at + timedelta(hours=1))

    run = tick()

    assert run.weeks_processed == 3
    assert run.trainer_salary_entries == 3
    entries = LedgerEntry.objects.filter(
        team=team, kind=LedgerEntry.Kind.TRAINER_SALARY,
    ).order_by("week__number")
    assert entries.count() == 3
    assert set(entries.values_list("week_id", flat=True)) == {
        season.weeks.get(number=n).pk for n in (1, 2, 3)
    }
    assert set(entries.values_list("occurred_at", flat=True)) == {
        season.weeks.get(number=n).starts_at for n in (1, 2, 3)
    }


def test_no_salary_row_for_unstaffed_team(db, team, riders):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    clock.set(week_one.starts_at + timedelta(hours=1))

    run = tick()

    assert run.trainer_salary_entries == 0
    assert not LedgerEntry.objects.filter(kind=LedgerEntry.Kind.TRAINER_SALARY).exists()


def test_tick_twice_charges_once(db, team, riders):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_two = season.weeks.get(number=2)
    make_trainer(team)
    clock.set(week_two.starts_at + timedelta(hours=1))

    first = tick()
    clock.set(season.weeks.get(number=3).starts_at + timedelta(hours=1))
    second = tick()

    assert first.trainer_salary_entries == 2
    assert second.trainer_salary_entries == 1
    rows = LedgerEntry.objects.filter(team=team, kind=LedgerEntry.Kind.TRAINER_SALARY)
    assert rows.count() == 3
    assert rows.values("week_id").distinct().count() == 3


def open_squad(team, level):
    return DevelopmentSquad.objects.create(team=team, level=level, opened_at=now())


def test_tick_charges_open_squad_each_crossed_week(db, team, riders):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_three = season.weeks.get(number=3)
    open_squad(team, 2)
    clock.set(week_three.starts_at + timedelta(hours=1))

    run = tick()

    assert run.weeks_processed == 3
    assert run.development_squad_entries == 3
    entries = LedgerEntry.objects.filter(
        team=team, kind=LedgerEntry.Kind.DEVELOPMENT_SQUAD,
    ).order_by("week__number")
    assert entries.count() == 3
    assert set(entries.values_list("amount", flat=True)) == {-3_500}
    assert set(entries.values_list("week_id", flat=True)) == {
        season.weeks.get(number=n).pk for n in (1, 2, 3)
    }
    assert set(entries.values_list("occurred_at", flat=True)) == {
        season.weeks.get(number=n).starts_at for n in (1, 2, 3)
    }
    assert entries.first().description == "Development squad — National"


def test_tick_charges_unmanaged_team_with_squad(db, riders):
    """An unmanaged team still runs the squad it was given, and its cost is
    real — the same argument that has its riders drawing wages and its trainer
    drawing a salary. Leaving them out would make a squad a free thing to hand
    to a team nobody is managing. Asserted against a managed team in the same
    tick, so the test fails if the map ever starts filtering on management."""
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    managed = managed_seller("SQX")
    unmanaged = Team.objects.create(name="SQY AI Team", code="SQY")
    open_squad(managed, 1)
    open_squad(unmanaged, 3)
    clock.set(season.weeks.get(number=1).starts_at + timedelta(hours=1))

    run = tick()

    assert run.development_squad_entries == 2
    charged = {
        entry.team_id: entry.amount
        for entry in LedgerEntry.objects.filter(kind=LedgerEntry.Kind.DEVELOPMENT_SQUAD)
    }
    assert charged == {managed.pk: -1_500, unmanaged.pk: -6_000}


def test_tick_twice_does_not_double_charge_squad(db, team, riders):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    open_squad(team, 3)
    clock.set(season.weeks.get(number=2).starts_at + timedelta(hours=1))

    first = tick()
    # Re-running the same tick, same clock: the (team, week) constraint has to
    # swallow the whole thing, not just the first duplicate.
    same_moment = tick()
    clock.set(season.weeks.get(number=3).starts_at + timedelta(hours=1))
    second = tick()

    assert first.development_squad_entries == 2
    assert same_moment.development_squad_entries == 0
    assert second.development_squad_entries == 1
    rows = LedgerEntry.objects.filter(team=team, kind=LedgerEntry.Kind.DEVELOPMENT_SQUAD)
    assert rows.count() == 3
    assert rows.values("week_id").distinct().count() == 3


def test_squad_opened_mid_week_first_charged_at_next_boundary(db, team, riders):
    """Design decision 7: no pro-rating, and no charge at the moment of
    opening. The tick only processes boundaries it has not seen, so a squad
    opened during week one is first charged when week two opens — and never
    for the week it opened in, which the opening fee is said to cover."""
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one, week_two = season.weeks.get(number=1), season.weeks.get(number=2)
    clock.set(week_one.starts_at + timedelta(hours=1))
    tick()                                   # week one's boundary, no squad yet
    assert not LedgerEntry.objects.filter(kind=LedgerEntry.Kind.DEVELOPMENT_SQUAD).exists()

    clock.set(week_one.starts_at + timedelta(days=3))
    open_squad(team, 2)                     # mid-week, after the boundary
    clock.set(week_two.starts_at + timedelta(hours=1))

    run = tick()

    assert run.development_squad_entries == 1
    entry = LedgerEntry.objects.get(team=team, kind=LedgerEntry.Kind.DEVELOPMENT_SQUAD)
    assert entry.week == week_two
    assert entry.occurred_at == week_two.starts_at


def test_no_squad_row_for_team_without_one(db, team, riders):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    clock.set(season.weeks.get(number=1).starts_at + timedelta(hours=1))

    run = tick()

    assert run.development_squad_entries == 0
    assert not LedgerEntry.objects.filter(kind=LedgerEntry.Kind.DEVELOPMENT_SQUAD).exists()


def test_squad_cost_follows_the_level_held_at_the_boundary(db, team, riders):
    """A mid-week upgrade is charged at the higher rate from the next
    boundary, with nothing prorated or refunded for the half-week just gone.

    Upwards is the only direction the ladder allows, and that is why the test
    does it this way: there is no downgrade to step down to, so while a squad
    is open its rate only ever rises.
    """
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one, week_two = season.weeks.get(number=1), season.weeks.get(number=2)
    open_squad(team, 1)
    clock.set(week_one.starts_at + timedelta(hours=1))
    tick()

    clock.set(week_one.starts_at + timedelta(days=3))
    change_level(team, 2, charge=lambda *_args, **_kwargs: None)
    clock.set(week_two.starts_at + timedelta(hours=1))
    tick()

    weekly = LedgerEntry.objects.filter(
        team=team, kind=LedgerEntry.Kind.DEVELOPMENT_SQUAD,
    ).order_by("week__number")
    assert [(e.week, e.amount, e.description) for e in weekly] == [
        (week_one, -1_500, "Development squad — Regional"),
        (week_two, -3_500, "Development squad — National"),
    ]


def test_tick_into_week_4_gives_open_squad_two_riders(db, team, riders):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_four = season.weeks.get(number=4)
    open_squad(team, 1)
    clock.set(week_four.starts_at + timedelta(hours=1))

    run = tick()

    assert run.youth_intake_riders == 2
    squad = DevelopmentSquad.objects.get(team=team)
    arrivals = Rider.objects.filter(development_squad=squad)
    assert arrivals.count() == 2
    for rider in arrivals:
        assert rider.team_id is None
        assert rider.intake_at == week_four.starts_at


def test_tick_into_week_5_gives_nothing(db, team, riders):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    open_squad(team, 1)
    clock.set(season.weeks.get(number=4).starts_at + timedelta(hours=1))
    tick()

    clock.set(season.weeks.get(number=5).starts_at + timedelta(hours=1))
    run = tick()

    assert run.youth_intake_riders == 0


def test_catch_up_across_weeks_3_to_9_gives_two_batches_dated_to_their_weeks(db, team, riders):
    # A single tick catching up weeks 4-9 crosses two intake weeks (4 and
    # 8), so it must write two SEPARATE batches, each dated to its own
    # week's starts_at — never one lump batch dated to whenever the tick
    # happened to run.
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_three = season.weeks.get(number=3)
    open_squad(team, 1)
    clock.set(week_three.starts_at + timedelta(hours=1))
    tick()

    week_nine = season.weeks.get(number=9)
    clock.set(week_nine.starts_at + timedelta(hours=1))
    run = tick()

    assert run.weeks_processed == 6  # weeks 4-9
    assert run.youth_intake_riders == 4  # two batches: weeks 4 and 8
    squad = DevelopmentSquad.objects.get(team=team)
    week_four = season.weeks.get(number=4)
    week_eight = season.weeks.get(number=8)
    assert set(
        Rider.objects.filter(development_squad=squad).values_list("intake_at", flat=True)
    ) == {week_four.starts_at, week_eight.starts_at}
    assert Rider.objects.filter(
        development_squad=squad, intake_at=week_four.starts_at,
    ).count() == 2
    assert Rider.objects.filter(
        development_squad=squad, intake_at=week_eight.starts_at,
    ).count() == 2


def test_tick_twice_does_not_duplicate_batch(db, team, riders):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_four = season.weeks.get(number=4)
    open_squad(team, 1)
    clock.set(week_four.starts_at + timedelta(hours=1))

    first = tick()
    same_moment = tick()

    assert first.youth_intake_riders == 2
    assert same_moment.youth_intake_riders == 0
    squad = DevelopmentSquad.objects.get(team=team)
    assert Rider.objects.filter(development_squad=squad).count() == 2


def test_released_team_with_squad_still_receives_intake(db, riders):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    unmanaged = Team.objects.create(name="Unmanaged Team", code="UNM")
    open_squad(unmanaged, 1)
    clock.set(season.weeks.get(number=4).starts_at + timedelta(hours=1))

    run = tick()

    assert run.youth_intake_riders == 2
    squad = DevelopmentSquad.objects.get(team=unmanaged)
    assert Rider.objects.filter(development_squad=squad).count() == 2


def test_squad_riders_draw_no_wages(db, team, riders):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_four = season.weeks.get(number=4)
    open_squad(team, 1)
    clock.set(week_four.starts_at + timedelta(hours=1))

    tick()

    roster_wage_bill = sum(r.weekly_salary for r in riders)
    wage_entry = LedgerEntry.objects.get(
        team=team, kind=LedgerEntry.Kind.WAGES, week=week_four,
    )
    assert wage_entry.amount == -roster_wage_bill


def test_squad_riders_get_no_trainer_focus_but_still_grow(db, team, riders):
    """A trainer with a focus is hired; the squad's own riders arrive at
    week 4 and are asserted to have moved by week 6's boundary — from
    growth alone, since a squad rider is never in
    trainer.team.riders.all()."""
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    make_trainer(team, climb=90)
    set_focus(team, "climb")
    open_squad(team, 1)
    clock.set(season.weeks.get(number=4).starts_at + timedelta(hours=1))
    tick()

    squad = DevelopmentSquad.objects.get(team=team)
    before = {
        r.pk: {attr: getattr(r, attr) for attr in ENGINE_ATTRIBUTES}
        for r in Rider.objects.filter(development_squad=squad)
    }

    # Two more weekly boundaries of ordinary age-curve growth, with no race
    # for any of them to have been trained by either.
    clock.set(season.weeks.get(number=6).starts_at + timedelta(hours=1))
    tick()

    for rider in Rider.objects.filter(development_squad=squad):
        moved = any(
            getattr(rider, attr) != before[rider.pk][attr] for attr in ENGINE_ATTRIBUTES
        )
        debt_nonzero = any(v != 0.0 for v in rider.growth_debt.values())
        # Growth is a small fraction of an attribute a week (WEEKLY_GROWTH_
        # FRACTION), so two weeks may or may not cross a whole stored point;
        # either way growth_debt must have accumulated something, proving
        # the age curve ran on them.
        assert moved or debt_nonzero


def test_new_arrivals_first_grow_the_following_week(db, team, riders):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_four = season.weeks.get(number=4)
    open_squad(team, 1)
    clock.set(week_four.starts_at + timedelta(hours=1))
    run = tick()

    squad = DevelopmentSquad.objects.get(team=team)
    arrivals = Rider.objects.filter(development_squad=squad)
    # Arrived this same week — run_intake runs AFTER _apply_training_week in
    # the loop body, so week 4's own growth pass has already happened
    # without them; nothing has moved them yet.
    assert run.youth_intake_riders == 2
    for rider in arrivals:
        assert rider.growth_debt == {}

    clock.set(season.weeks.get(number=5).starts_at + timedelta(hours=1))
    tick()

    for rider in arrivals:
        rider.refresh_from_db()
        # The following week's boundary is the first growth pass to reach
        # them: growth_debt has accumulated something, or a stored
        # attribute already crossed a whole point.
        assert rider.growth_debt != {} or any(
            getattr(rider, attr) != 1 for attr in ("climb", "sprint", "flat", "resistance", "positioning")
        )


def test_week_one_has_no_preceding_week_and_only_decays(db, team, riders):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    give_starting_fanbase(team, at=now())
    clock.set(week_one.starts_at + timedelta(hours=1))

    run = tick()

    assert run.fanbase_entries == 1
    row = FanbaseEntry.objects.get(team=team, kind=FanbaseEntry.Kind.WEEKLY)
    assert row.week == week_one
    assert row.points == 0
    assert row.delta == -WEEKLY_FANBASE_DECAY
    assert sum(FanbaseEntry.objects.filter(team=team).values_list("delta", flat=True)) == (
        STARTING_FANBASE - WEEKLY_FANBASE_DECAY
    )


def test_fanbase_reads_the_completed_week_not_the_opening_one(db, team, riders):
    # The load-bearing test for D2: entering week 2 must adjust fanbase off
    # week 1's points, because week 2's own races have not run yet when its
    # week transition is processed. An implementation that reads the opening
    # week gets points == 0 and a pure-decay delta.
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    week_two = season.weeks.get(number=2)
    give_starting_fanbase(team, at=now())
    Race.objects.create(
        name="Week One Race",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=week_one.starts_at + timedelta(hours=1),
        status=Race.Status.SCHEDULED,
        week=week_one,
    )

    clock.set(week_one.starts_at + timedelta(hours=1))
    tick()  # week 1 opens: pure decay, then the race is run and scored

    clock.set(week_two.starts_at + timedelta(hours=1))
    tick()  # week 2 opens: now week 1's points land

    week_two_row = FanbaseEntry.objects.get(
        team=team, kind=FanbaseEntry.Kind.WEEKLY, week=week_two
    )
    assert week_two_row.points > 0
    assert week_two_row.delta > -WEEKLY_FANBASE_DECAY

    week_one_row = FanbaseEntry.objects.get(
        team=team, kind=FanbaseEntry.Kind.WEEKLY, week=week_one
    )
    assert week_one_row.points == 0  # the week's own races come later
    assert week_one_row.delta == -WEEKLY_FANBASE_DECAY


def test_tick_pays_merchandise_after_updating_fanbase(db, team, riders):
    # The load-bearing test for D7: merchandise must be paid off the
    # post-adjustment fanbase, not whatever it was before this week's change.
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    week_two = season.weeks.get(number=2)
    give_starting_fanbase(team, at=now())
    Race.objects.create(
        name="Week One Race",
        course=[{"length": 500.0, "gradient": 0.0}],
        starts_at=week_one.starts_at + timedelta(hours=1),
        status=Race.Status.SCHEDULED,
        week=week_one,
    )

    clock.set(week_one.starts_at + timedelta(hours=1))
    tick()

    before = sum(FanbaseEntry.objects.filter(team=team).values_list("delta", flat=True))

    clock.set(week_two.starts_at + timedelta(hours=1))
    tick()

    week_two_row = FanbaseEntry.objects.get(
        team=team, kind=FanbaseEntry.Kind.WEEKLY, week=week_two
    )
    after = before + week_two_row.delta
    assert after > before  # the fanbase actually moved this week

    entry = LedgerEntry.objects.get(
        team=team, kind=LedgerEntry.Kind.MERCHANDISE, week=week_two
    )
    assert entry.amount == after // MERCHANDISE_FANBASE_PER_CREDIT


def test_catch_up_across_three_weeks_writes_three_fanbase_and_three_merchandise_entries(
    db, team, riders
):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_three = season.weeks.get(number=3)
    give_starting_fanbase(team, at=now())
    clock.set(week_three.starts_at + timedelta(hours=1))

    run = tick()

    assert run.weeks_processed == 3
    assert run.fanbase_entries == 3
    assert run.merchandise_entries == 3
    fanbase_rows = FanbaseEntry.objects.filter(
        team=team, kind=FanbaseEntry.Kind.WEEKLY
    ).order_by("week__number")
    assert fanbase_rows.count() == 3
    assert set(fanbase_rows.values_list("week_id", flat=True)) == {
        season.weeks.get(number=n).pk for n in (1, 2, 3)
    }
    assert set(fanbase_rows.values_list("occurred_at", flat=True)) == {
        season.weeks.get(number=n).starts_at for n in (1, 2, 3)
    }
    merch_rows = LedgerEntry.objects.filter(
        team=team, kind=LedgerEntry.Kind.MERCHANDISE
    ).order_by("week__number")
    assert merch_rows.count() == 3
    assert set(merch_rows.values_list("occurred_at", flat=True)) == {
        season.weeks.get(number=n).starts_at for n in (1, 2, 3)
    }


def test_tick_run_counts_fanbase_and_merchandise_entries(db, team, riders):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    give_starting_fanbase(team, at=now())
    clock.set(week_one.starts_at + timedelta(hours=1))

    run = tick()

    assert run.fanbase_entries == 1
    assert run.merchandise_entries == 1
    assert FanbaseEntry.objects.filter(team=team, kind=FanbaseEntry.Kind.WEEKLY).count() == 1
    assert LedgerEntry.objects.filter(
        team=team, kind=LedgerEntry.Kind.MERCHANDISE
    ).count() == 1


def test_tick_generates_offer_rounds_on_season_open(db, team, riders):
    _give_a_manager(team)
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    clock.set(week_one.starts_at + timedelta(hours=1))

    tick()  # crosses the season's own starts_at boundary as well as week 1's

    assert SponsorOffer.objects.filter(team=team, season=season).count() == 3


def test_offer_rounds_are_not_duplicated_by_a_second_tick(db, team, riders):
    _give_a_manager(team)
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_two = season.weeks.get(number=2)
    clock.set(week_two.starts_at + timedelta(hours=1))

    tick()
    clock.set(season.weeks.get(number=3).starts_at + timedelta(hours=1))
    tick()

    assert SponsorOffer.objects.filter(team=team, season=season).count() == 3


def test_tick_pays_sponsorship_for_contracted_teams(db, team, riders):
    _give_a_manager(team)
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    clock.set(week_one.starts_at + timedelta(hours=1))
    tick()  # generates the offer round

    offer = SponsorOffer.objects.filter(team=team, season=season).first()
    contract = sign_offer(team, offer.pk, at=now())

    week_two = season.weeks.get(number=2)
    clock.set(week_two.starts_at + timedelta(hours=1))
    run = tick()

    assert run.sponsorship_entries == 1
    entry = LedgerEntry.objects.get(team=team, kind=LedgerEntry.Kind.SPONSORSHIP, week=week_two)
    assert contract.floor_amount <= entry.amount <= contract.ceiling_amount


def test_catch_up_tick_pays_each_week_separately(db, team, riders):
    _give_a_manager(team)
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    clock.set(week_one.starts_at + timedelta(hours=1))
    tick()

    offer = SponsorOffer.objects.filter(team=team, season=season).first()
    sign_offer(team, offer.pk, at=now())

    week_four = season.weeks.get(number=4)
    clock.set(week_four.starts_at + timedelta(hours=1))
    run = tick()

    assert run.sponsorship_entries == 3
    assert LedgerEntry.objects.filter(
        team=team, kind=LedgerEntry.Kind.SPONSORSHIP,
    ).count() == 3


def managed_seller(code: str) -> Team:
    manager = User.objects.create_user(
        email=f"{code.lower()}-seller@example.com", password="s0meth1ng-good",
    )
    return Team.objects.create(name=f"{code} Human Team", code=code, manager=manager)


def ai_buyer(code: str, *, roster: int = 12) -> Team:
    team = Team.objects.create(name=f"{code} AI Team", code=code)
    ensure_opening_balance(team, at=now())
    for i in range(roster):
        Rider.objects.create(
            name=f"{code} Domestique {i}", team=team, age=27,
            climb=40, sprint=40, flat=40, resistance=40, positioning=40,
        )
    return team


def rider_for(name: str, team: Team, *, level: int = 60) -> Rider:
    return Rider.objects.create(
        name=name, team=team, age=27,
        climb=level, sprint=level, flat=level, resistance=level, positioning=level,
    )


def test_tick_places_ai_bids_without_a_week_transition(db):
    # No season is declared, so the AI's listing side has no week to act on —
    # but its buying side is keyed to wall-clock deadlines and must still run.
    seller = managed_seller("SEL")
    listed = rider_for("For Sale", seller)
    auction = list_for_auction(seller, listed.pk, at=now())
    ai = ai_buyer("AIA")

    run = tick()

    assert run.weeks_processed == 0
    assert run.ai_listings_created == 0
    assert run.ai_bids_placed == 1
    assert auction.bids.live().get().bidder_team_id == ai.pk


def test_tick_lists_ai_riders_once_when_catching_up_several_weeks(db):
    clock: MockClock = get_clock()
    # The listing stagger is (week.number + team.pk) % AI_LISTING_EVERY_WEEKS
    # == 0 and pks depend on the sequence, so add teams until this one's
    # third week — the last the tick below will cross — is its own.
    filler = 0
    while True:
        ai = Team.objects.create(name=f"AI {filler}", code=f"A{filler:02d}")
        filler += 1
        if (3 + ai.pk) % AI_LISTING_EVERY_WEEKS == 0:
            break
    for i in range(12):
        Rider.objects.create(
            name=f"{ai.code} Domestique {i}", team=ai, age=27,
            climb=40, sprint=40, flat=40, resistance=40, positioning=40,
        )
    rider_for("Surplus", ai, level=30)
    season = make_season_with_weeks(1, now() - timedelta(weeks=2))
    clock.set(season.weeks.get(number=3).starts_at + timedelta(hours=1))

    run = tick()

    assert run.weeks_processed == 3
    assert run.ai_listings_created == 1
    assert Auction.objects.get(seller_team=ai, status=Auction.Status.OPEN).rider.name == "Surplus"


def test_tick_resolves_before_ai_bids(db):
    # The auction is due this tick, so it resolves UNSOLD: the AI must not
    # rescue a listing it can no longer win by bidding on it first.
    clock: MockClock = get_clock()
    seller = managed_seller("SEL")
    listed = rider_for("For Sale", seller)
    auction = list_for_auction(seller, listed.pk, at=now())
    ai_buyer("AIA")
    clock.set(auction.deadline + timedelta(hours=1))

    run = tick()

    assert run.auctions_unsold == 1
    assert run.ai_bids_placed == 0
    auction.refresh_from_db()
    assert auction.status == Auction.Status.UNSOLD
    assert auction.bids.exists() is False


def _explode(*args, **kwargs):
    raise RuntimeError("the ledger is on fire")


def test_a_failing_ai_bid_is_recorded_on_the_run_and_the_week_still_settles(db, monkeypatch):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now() - timedelta(weeks=1))
    seller = managed_seller("SEL")
    listed = rider_for("For Sale", seller)
    auction = list_for_auction(seller, listed.pk, at=now())
    ai_buyer("AIA")
    clock.set(season.weeks.get(number=1).starts_at + timedelta(hours=1))
    monkeypatch.setattr("world.ai_market.place_bid", _explode)

    run = tick()

    assert run.ai_bids_placed == 0
    assert f"ai bid on auction {auction.pk}" in run.error
    assert "RuntimeError: the ledger is on fire" in run.error
    # The tick's own work is untouched by the AI market failing.
    assert run.weeks_processed == 1
    assert run.wage_entries >= 1
    assert run.finished_at is not None
    assert auction.bids.exists() is False


def test_a_failing_ai_balance_read_is_recorded_on_the_run(db, monkeypatch):
    # balance_for is called once per unmanaged team while the buyer table is
    # built, before any per-auction guard exists. That read failing must not
    # take the tick down with it.
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now() - timedelta(weeks=1))
    ai_buyer("AIA")
    clock.set(season.weeks.get(number=1).starts_at + timedelta(hours=1))
    monkeypatch.setattr("world.ai_market.balance_for", _explode)

    run = tick()

    assert run.ai_bids_placed == 0
    assert "ai market:" in run.error
    assert "RuntimeError: the ledger is on fire" in run.error
    assert run.weeks_processed == 1
    assert run.wage_entries >= 1
    assert run.finished_at is not None


def test_ai_won_auction_moves_rider_and_money_end_to_end(db):
    clock: MockClock = get_clock()
    seller = managed_seller("SEL")
    listed = rider_for("For Sale", seller)
    auction = list_for_auction(seller, listed.pk, at=now())
    ai = ai_buyer("AIA")
    tick()

    clock.set(auction.deadline + timedelta(hours=1))
    run = tick()

    assert run.ai_bids_placed == 0
    assert run.auctions_sold == 1
    listed.refresh_from_db()
    assert listed.team_id == ai.pk
    assert LedgerEntry.objects.filter(
        team=ai, kind=LedgerEntry.Kind.TRANSFER_FEE, amount=-auction.reserve_price,
    ).exists()
    assert LedgerEntry.objects.filter(
        team=seller, kind=LedgerEntry.Kind.TRANSFER_FEE, amount=auction.reserve_price,
    ).exists()


# --- The AI management (#45) -------------------------------------------------


def _ai_team(code: str, *, speciality: str = Rider.Speciality.ROULEUR) -> Team:
    team = Team.objects.create(name=f"{code} AI Team", code=code)
    ensure_opening_balance(team, at=now())
    give_starting_fanbase(team, now())
    for i in range(4):
        Rider.objects.create(
            name=f"{code} Rider {i}", team=team, speciality=speciality,
            climb=60, sprint=60, flat=60, resistance=60, positioning=60,
            weekly_salary=1000,
        )
    return team


def test_season_open_signs_every_unmanaged_team_steady_and_pays_week_one(db):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    ai_teams = [_ai_team("AIA"), _ai_team("AIB")]
    human = managed_seller("HUM")
    clock.set(week_one.starts_at + timedelta(hours=1))

    run = tick()

    assert run.ai_sponsors_signed == 2
    for team in ai_teams:
        assert active_contract(team, season).profile == "steady"
        assert LedgerEntry.objects.filter(
            team=team, kind=LedgerEntry.Kind.SPONSORSHIP, week=week_one,
        ).exists()
    assert active_contract(human, season) is None


def test_week_boundary_hires_and_the_salary_starts_the_week_after(db):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    week_two = season.weeks.get(number=2)
    team = _ai_team("AIA")
    trainer = Trainer.objects.create(
        name="Coach", climb=70, sprint=50, flat=50, resistance=50, positioning=50,
    )
    clock.set(week_one.starts_at + timedelta(hours=1))

    run = tick()

    assert run.ai_trainers_hired == 1
    trainer.refresh_from_db()
    assert trainer.team == team
    assert LedgerEntry.objects.filter(team=team, kind=LedgerEntry.Kind.TRAINER_FEE).count() == 1
    assert not LedgerEntry.objects.filter(team=team, kind=LedgerEntry.Kind.TRAINER_SALARY).exists()

    clock.set(week_two.starts_at + timedelta(hours=1))
    second = tick()

    assert second.ai_trainers_hired == 0
    salary = LedgerEntry.objects.get(team=team, kind=LedgerEntry.Kind.TRAINER_SALARY)
    assert salary.week == week_two
    assert salary.amount == -weekly_salary(trainer)
    assert LedgerEntry.objects.filter(team=team, kind=LedgerEntry.Kind.TRAINER_FEE).count() == 1


def test_the_ai_focus_is_the_one_that_week_trains_on(db):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    team = _ai_team("AIA", speciality=Rider.Speciality.SPRINTER)
    Trainer.objects.create(
        name="Coach", team=team, climb=70, sprint=50, flat=50, resistance=50, positioning=50,
    )
    expected = focus_for_week(list(team.riders.all()), week_one.number, team.pk)
    # Not the default focus, or a focus set after training would still pass.
    assert expected == "sprint"
    clock.set(week_one.starts_at + timedelta(hours=1))

    tick()

    assert TrainingWeekReport.objects.get(team=team, week=week_one).attribute == expected


def test_a_failing_ai_hire_is_recorded_and_the_tick_still_charges_wages(db, monkeypatch):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    team = _ai_team("AIA")

    def _raise(at):
        raise RuntimeError("boom")

    monkeypatch.setattr("world.services.hire_ai_trainers", _raise)
    clock.set(week_one.starts_at + timedelta(hours=1))

    run = tick()

    assert "ai management" in run.error
    assert "boom" in run.error
    assert LedgerEntry.objects.filter(team=team, kind=LedgerEntry.Kind.WAGES, week=week_one).exists()
