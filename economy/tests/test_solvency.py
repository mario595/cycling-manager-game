from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone

import pytest

from economy.models import FanbaseEntry, SolvencyCheck, SponsorContract
from economy.solvency import (
    INSOLVENCY_LOSS_STRIKES,
    is_embargoed,
    open_check,
    regular_income,
    solvency_status,
    weekly_shortfall,
)
from riders.models import Rider
from schedule.models import Season, Week

START = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)


@pytest.fixture
def season(db) -> Season:
    return Season.objects.create(number=1, starts_at=START)


@pytest.fixture
def weeks(season) -> list[Week]:
    return [
        Week.objects.create(
            season=season, number=n,
            starts_at=START + timedelta(weeks=n - 1),
            ends_at=START + timedelta(weeks=n),
        )
        for n in range(1, 9)
    ]


def _rider(team, salary: int) -> Rider:
    return Rider.objects.create(
        team=team, name=f"Rider {salary}", weekly_salary=salary,
        climb=60, sprint=50, flat=60, resistance=55, positioning=45,
    )


def _fanbase(team, fans: int) -> None:
    FanbaseEntry.objects.create(
        team=team, kind=FanbaseEntry.Kind.STARTING, delta=fans,
        occurred_at=START, description="Starting fanbase",
    )


def _check(team, week, *, balance=-100, shortfall=50, strikes=1) -> SolvencyCheck:
    return SolvencyCheck.objects.create(
        team=team, week=week, occurred_at=week.starts_at,
        balance=balance, shortfall=shortfall, strikes=strikes,
    )


def test_shortfall_is_outgoings_minus_income_floored_at_zero(db, team, season):
    _rider(team, 1_000)
    _rider(team, 500)
    _fanbase(team, 2_500)                       # merchandise 100

    assert weekly_shortfall(team, season, trainer_salary=200, squad_cost=300) == 1_900
    # More income than outgoings is a zero, never negative.
    _fanbase(team, 500_000)
    assert weekly_shortfall(team, season, trainer_salary=0, squad_cost=0) == 0


def test_income_counts_sponsor_base_not_weekly_payment(db, team, season):
    _fanbase(team, 2_500)                       # merchandise 100
    SponsorContract.objects.create(
        team=team, season=season, profile="demanding", sponsor_name="Velocore",
        weekly_base=700, floor_amount=100, ceiling_amount=2_000, sensitivity=1.0,
        signed_at=START,
    )

    assert regular_income(team, season) == 800


def test_income_without_season_is_merchandise_only(db, team):
    _fanbase(team, 2_500)

    assert regular_income(team, None) == 100


def test_open_check_ignores_checks_before_managed_since(db, team, weeks):
    _check(team, weeks[0])
    team.managed_since = weeks[1].starts_at          # claimed after that check
    team.save()

    assert open_check(team) is None
    assert is_embargoed(team) is False


def test_open_check_needs_a_negative_latest_check(db, team, weeks):
    _check(team, weeks[0], balance=-100)
    _check(team, weeks[1], balance=40, shortfall=0, strikes=0)    # recovery row

    assert open_check(team) is None


def test_status_paydays_left_and_deadline(db, team, season, weeks):
    _rider(team, 1_000)
    _check(team, weeks[0], strikes=1, shortfall=1_000)

    status = solvency_status(team, season, trainer_salary=0, squad_cost=0)

    assert status.insolvent is True
    assert status.paydays_left == INSOLVENCY_LOSS_STRIKES - 1
    assert status.deadline == weeks[3].starts_at     # third week after the check


def test_status_deadline_none_when_weeks_not_declared(db, team, season, weeks):
    _rider(team, 1_000)
    _check(team, weeks[-1], strikes=1, shortfall=1_000)

    status = solvency_status(team, season, trainer_salary=0, squad_cost=0)

    assert status.paydays_left == 3
    assert status.deadline is None


def test_status_paydays_left_none_when_live_shortfall_zero(db, team, season, weeks):
    _fanbase(team, 500_000)
    _check(team, weeks[0], strikes=2, shortfall=300)

    status = solvency_status(team, season, trainer_salary=0, squad_cost=0)

    assert status.insolvent is True
    assert status.shortfall == 0
    assert status.paydays_left is None
    assert status.deadline is None


def test_cut_so_far_is_target_minus_live_shortfall(db, team, season, weeks):
    _rider(team, 700)
    _check(team, weeks[0], strikes=1, shortfall=1_000)

    status = solvency_status(team, season, trainer_salary=0, squad_cost=0)

    assert status.target == 1_000
    assert status.shortfall == 700
    assert status.cut_so_far == 300


def test_status_when_solvent_reports_live_numbers(db, team, season):
    _rider(team, 700)

    status = solvency_status(team, season, trainer_salary=0, squad_cost=0)

    assert status.insolvent is False
    assert status.shortfall == 700
    assert status.paydays_left is None
