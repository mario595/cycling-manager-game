from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone

import pytest

from economy.models import LedgerEntry
from economy.services import balance_for, charge_weekly_wages, payroll_for
from riders.models import Rider
from schedule.models import Season, Week
from teams.models import Team


@pytest.fixture
def season(db) -> Season:
    return Season.objects.create(
        number=1,
        starts_at=datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc),
    )


@pytest.fixture
def week(season) -> Week:
    return Week.objects.create(
        season=season,
        number=1,
        starts_at=season.starts_at,
        ends_at=season.starts_at + timedelta(weeks=1),
    )


def _rider(team, **overrides) -> Rider:
    defaults = dict(
        name="Rider One",
        climb=70, sprint=50, flat=60, resistance=55, positioning=45,
    )
    defaults.update(overrides)
    return Rider.objects.create(team=team, **defaults)


def test_charges_every_team_once(db, team, other_team, week):
    _rider(team)
    _rider(other_team)

    written = charge_weekly_wages(week)

    assert written == 2
    assert LedgerEntry.objects.filter(kind=LedgerEntry.Kind.WAGES, week=week).count() == 2


def test_amount_is_sum_of_actual_salaries(db, team, week):
    # Riders with deliberately distinct salaries (#25) — proves the charge
    # is a real sum, not a head count times a flat rate.
    _rider(team, weekly_salary=1000)
    _rider(team, weekly_salary=2500)
    _rider(team, weekly_salary=1750)

    charge_weekly_wages(week)

    entry = LedgerEntry.objects.get(team=team, week=week)
    assert entry.amount == -(1000 + 2500 + 1750)
    assert entry.rider_count == 3


def test_unmanaged_teams_are_charged(db, week):
    unmanaged_team = Team.objects.create(name="Unmanaged", code="UNM")
    _rider(unmanaged_team)

    charge_weekly_wages(week)

    assert unmanaged_team.manager_id is None
    assert LedgerEntry.objects.filter(
        team=unmanaged_team, kind=LedgerEntry.Kind.WAGES, week=week,
    ).count() == 1


def test_empty_roster_is_charged_zero_not_skipped(db, team, week):
    charge_weekly_wages(week)

    entry = LedgerEntry.objects.get(team=team, week=week)
    assert entry.amount == 0
    assert entry.rider_count == 0
    assert balance_for(team) == 0


def test_second_call_for_same_week_writes_nothing(db, team, week):
    _rider(team, weekly_salary=1800)
    charge_weekly_wages(week)
    first = LedgerEntry.objects.get(team=team, week=week)
    total_after_first = LedgerEntry.objects.filter(team=team).count()

    assert charge_weekly_wages(week) == 0

    first.refresh_from_db()
    assert first.amount == -1800
    assert LedgerEntry.objects.filter(team=team).count() == total_after_first


def test_occurred_at_is_the_weeks_start(db, team, week):
    _rider(team)

    charge_weekly_wages(week)

    entry = LedgerEntry.objects.get(team=team, week=week)
    assert entry.occurred_at == week.starts_at


def test_payroll_for_sums_the_teams_current_salaries(db, team):
    _rider(team, weekly_salary=1000)
    _rider(team, weekly_salary=2500)

    assert payroll_for(team) == 3500


def test_payroll_for_empty_roster_is_zero(db, team):
    assert payroll_for(team) == 0