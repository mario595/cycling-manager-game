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
from economy.services import ensure_opening_balance, sign_offer
from racing.models import Race, RaceMarker, RaceResult
from riders.development_squad import change_level
from riders.models import ENGINE_ATTRIBUTES, DevelopmentSquad, Rider
from staff.services import set_focus
from schedule.models import SEASON_WEEKS, Season, Week
from staff.models import Trainer
from staff.pricing import weekly_salary
from teams.models import Team
from transfers.models import Auction
from transfers.services import list_for_auction
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
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_one = season.weeks.get(number=1)
    clock.set(week_one.starts_at + timedelta(hours=1))

    tick()  # crosses the season's own starts_at boundary as well as week 1's

    assert SponsorOffer.objects.filter(team=team, season=season).count() == 3


def test_offer_rounds_are_not_duplicated_by_a_second_tick(db, team, riders):
    clock: MockClock = get_clock()
    season = make_season_with_weeks(1, now())
    week_two = season.weeks.get(number=2)
    clock.set(week_two.starts_at + timedelta(hours=1))

    tick()
    clock.set(season.weeks.get(number=3).starts_at + timedelta(hours=1))
    tick()

    assert SponsorOffer.objects.filter(team=team, season=season).count() == 3


def test_tick_pays_sponsorship_for_contracted_teams(db, team, riders):
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
