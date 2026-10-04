from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone

import pytest

from accounts.models import User
from economy.models import FanbaseEntry, LedgerEntry, SolvencyCheck, SponsorContract
from economy.solvency import (
    INSOLVENCY_LOSS_STRIKES,
    assess_solvency,
    is_embargoed,
    open_check,
    regular_income,
    solvency_status,
    weekly_shortfall,
)
from riders.models import Rider
from schedule.models import Season, Week
from teams.models import Team

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


# -- assess_solvency -------------------------------------------------------

@pytest.fixture
def managed(db) -> Team:
    user = User.objects.create_user(email="m@example.com", password="s0meth1ng-good")
    return Team.objects.create(name="Managed", code="MAN", manager=user)


def _balance(team, amount: int) -> None:
    LedgerEntry.objects.create(
        team=team, kind=LedgerEntry.Kind.STARTING_BALANCE, amount=amount,
        occurred_at=START, description="Test balance",
    )


def _assess(week):
    return assess_solvency(week, salary_by_team={}, squad_cost_by_team={})


def test_solvent_team_without_case_writes_nothing(db, managed, weeks):
    _balance(managed, 1_000)

    outcome = _assess(weeks[0])

    assert outcome.written == 0
    assert SolvencyCheck.objects.count() == 0


def test_negative_balance_opens_case_with_one_strike(db, managed, weeks):
    _rider(managed, 500)
    _balance(managed, -1)

    outcome = _assess(weeks[0])

    check = SolvencyCheck.objects.get(team=managed)
    assert (check.strikes, check.shortfall, check.balance) == (1, 500, -1)
    assert outcome.opened == [managed.pk]
    assert outcome.lost == []


def test_case_opens_with_zero_strikes_when_no_shortfall(db, managed, weeks):
    _fanbase(managed, 500_000)
    _balance(managed, -1)

    _assess(weeks[0])

    assert SolvencyCheck.objects.get(team=managed).strikes == 0


def test_strikes_accumulate_while_shortfall_open(db, managed, weeks):
    _rider(managed, 500)
    _balance(managed, -1)

    for week in weeks[:3]:
        _assess(week)

    assert list(
        SolvencyCheck.objects.filter(team=managed).order_by("occurred_at").values_list("strikes", flat=True)
    ) == [1, 2, 3]


def test_meeting_target_resets_strikes(db, managed, weeks):
    rider = _rider(managed, 500)
    _balance(managed, -1)
    _assess(weeks[0])
    _assess(weeks[1])
    rider.delete()                              # the shortfall is cut

    _assess(weeks[2])

    assert SolvencyCheck.objects.get(team=managed, week=weeks[2]).strikes == 0


def test_new_breach_after_reset_starts_at_one(db, managed, weeks):
    rider = _rider(managed, 500)
    _balance(managed, -1)
    _assess(weeks[0])
    rider.delete()
    _assess(weeks[1])                           # strikes reset to 0
    _rider(managed, 500)                        # wages come back, e.g. a salary review

    _assess(weeks[2])

    assert SolvencyCheck.objects.get(team=managed, week=weeks[2]).strikes == 1


def test_recovery_row_closes_case(db, managed, weeks):
    _rider(managed, 500)
    _balance(managed, -1)
    _assess(weeks[0])
    assert is_embargoed(managed) is True
    _balance(managed, 10_000)

    outcome = _assess(weeks[1])

    recovery = SolvencyCheck.objects.get(team=managed, week=weeks[1])
    assert recovery.strikes == 0
    assert recovery.balance >= 0
    assert outcome.opened == [] and outcome.lost == []
    assert is_embargoed(managed) is False


def test_fourth_strike_is_reported_lost(db, managed, weeks):
    _rider(managed, 500)
    _balance(managed, -1)

    outcomes = [_assess(week) for week in weeks[:INSOLVENCY_LOSS_STRIKES]]

    assert [o.lost for o in outcomes] == [[], [], [], [managed.pk]]


def test_unmanaged_teams_are_never_assessed(db, team, weeks):
    _rider(team, 500)
    _balance(team, -1)

    assert _assess(weeks[0]).written == 0


def test_team_claimed_after_boundary_is_skipped(db, managed, weeks):
    _rider(managed, 500)
    _balance(managed, -1)
    managed.managed_since = weeks[1].starts_at
    managed.save()

    assert _assess(weeks[0]).written == 0


def test_reassessing_same_week_writes_and_reports_nothing(db, managed, weeks):
    _rider(managed, 500)
    _balance(managed, -1)
    for week in weeks[:3]:
        _assess(week)
    _assess(weeks[3])                           # the fourth strike: lost

    again = _assess(weeks[3])

    assert again.written == 0
    assert again.opened == [] and again.lost == []
    assert SolvencyCheck.objects.filter(team=managed).count() == 4


def test_forced_listing_counts_before_payday(db, managed, weeks):
    rider = _rider(managed, 500)
    _balance(managed, -1)
    rider.team = None                           # a forced sale happened mid-week
    rider.save()

    _assess(weeks[0])

    assert SolvencyCheck.objects.get(team=managed).shortfall == 0
