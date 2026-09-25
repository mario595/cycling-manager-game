from __future__ import annotations

from datetime import timedelta

import pytest

from accounts.models import User
from economy.models import (
    MERCHANDISE_FANBASE_PER_CREDIT,
    STARTING_FANBASE,
    WEEKLY_FANBASE_DECAY,
    FanbaseEntry,
    LedgerEntry,
    SponsorOffer,
)
from economy.services import ensure_opening_balance, sign_offer
from racing.models import Race, RaceResult
from riders.models import Rider
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
