from __future__ import annotations

from datetime import timedelta

import pytest

from accounts.models import User
from economy.models import LedgerEntry, SolvencyCheck
from economy.solvency import is_embargoed
from riders.models import Rider
from schedule.models import SEASON_WEEKS, Season, Week
from teams.models import ManagerialSpell, Team
from teams.services import claim_team
from transfers.models import Auction, Bid
from transfers.services import list_for_auction, place_bid
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
def manager(db) -> User:
    return User.objects.create_user(email="manager@example.com", password="s0meth1ng-good")


@pytest.fixture
def season(db) -> Season:
    return make_season_with_weeks(1, now())


@pytest.fixture
def team(db, manager, season) -> Team:
    """A managed team that cannot pay its way: a wage bill, no income to
    speak of, and a balance already below zero."""
    team = Team.objects.create(name="Team Alpha", code="ALP", manager=manager)
    for i in range(6):
        Rider.objects.create(
            team=team, name=f"Rider {i}", weekly_salary=5_000,
            climb=60, sprint=60, flat=60, resistance=60, positioning=60,
        )
    LedgerEntry.objects.create(
        team=team, kind=LedgerEntry.Kind.STARTING_BALANCE, amount=-1,
        occurred_at=season.starts_at, description="Test balance",
    )
    return team


def _tick_at_week(season, number):
    get_clock().set(season.weeks.get(number=number).starts_at + timedelta(hours=1))
    return tick()


def test_tick_opens_case_for_negative_managed_team(db, team, season):
    run = _tick_at_week(season, 1)

    check = SolvencyCheck.objects.get(team=team)
    assert check.strikes == 1
    assert run.solvency_checks == 1
    assert is_embargoed(team) is True


def test_tick_withdraws_live_bids_when_case_opens(db, team, season):
    other = Team.objects.create(name="Seller", code="SEL")
    rider = Rider.objects.create(
        team=other, name="For Sale",
        climb=60, sprint=60, flat=60, resistance=60, positioning=60,
    )
    auction = list_for_auction(other, rider.pk, at=now())
    place_bid(auction.pk, team, auction.reserve_price, at=now())

    _tick_at_week(season, 1)

    assert Bid.objects.live().filter(bidder_team=team).count() == 0
    auction.refresh_from_db()
    assert auction.status == Auction.Status.OPEN
    assert auction.current_price == auction.reserve_price


def test_tick_releases_team_on_fourth_unmet_payday(db, team, season):
    for number in (1, 2, 3):
        run = _tick_at_week(season, number)
        team.refresh_from_db()
        assert team.manager_id is not None
        assert run.teams_lost_to_insolvency == 0

    run = _tick_at_week(season, 4)

    team.refresh_from_db()
    assert team.manager_id is None
    assert run.teams_lost_to_insolvency == 1
    assert run.teams_released == 0
    spell = ManagerialSpell.objects.get()
    assert spell.reason == ManagerialSpell.Reason.INSOLVENCY


def test_tick_keeps_team_whose_target_is_met(db, team, season):
    _tick_at_week(season, 1)
    _tick_at_week(season, 2)
    team.riders.all().delete()                 # the shortfall is cut

    for number in range(3, 8):
        _tick_at_week(season, number)

    team.refresh_from_db()
    assert team.manager_id is not None
    assert SolvencyCheck.objects.filter(team=team, week__number=7).get().strikes == 0


def test_catch_up_across_four_weeks_releases_once(db, team, season):
    run = _tick_at_week(season, 4)             # weeks 1-4 all crossed in one tick

    assert run.weeks_processed == 4
    assert run.teams_lost_to_insolvency == 1
    assert ManagerialSpell.objects.count() == 1
    assert SolvencyCheck.objects.filter(team=team).count() == 4


def test_insolvency_runs_before_inactivity(db, team, manager, season):
    manager.last_seen_at = season.weeks.get(number=1).starts_at
    manager.save(update_fields=["last_seen_at"])

    run = _tick_at_week(season, 11)            # due for both along the way

    assert run.teams_lost_to_insolvency == 1
    assert run.teams_released == 0
    assert ManagerialSpell.objects.get().reason == ManagerialSpell.Reason.INSOLVENCY


def test_claimed_team_starts_solvent(db, team, season):
    _tick_at_week(season, 4)                   # lost
    newcomer = User.objects.create_user(email="new@example.com", password="s0meth1ng-good")
    claimed = claim_team(newcomer, name="Fresh Start", code="FRS", at=now())

    assert is_embargoed(claimed) is False

    run = _tick_at_week(season, 5)

    assert run.solvency_checks == 0
    assert SolvencyCheck.objects.filter(team=claimed, week__number=5).count() == 0
    assert is_embargoed(claimed) is False
