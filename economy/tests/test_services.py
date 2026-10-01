from __future__ import annotations

from datetime import datetime, timezone as dt_timezone

import pytest

from accounts.models import User
from economy.models import STARTING_BALANCE, LedgerEntry, SalaryReviewReport
from economy.services import (
    balance_for,
    charge_transfer_fee,
    ensure_opening_balance,
    entries_for,
    latest_salary_review,
    pay_gc_prizes,
    pay_race_prizes,
    pay_transfer_income,
    reset_to_starting_balance,
    write_salary_reviews,
)
from riders.models import Rider
from schedule.models import Season
from teams.models import Team


@pytest.fixture
def season(db) -> Season:
    monday = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    return Season.objects.create(number=1, starts_at=monday)


@pytest.fixture
def managed_team(db) -> Team:
    manager = User.objects.create_user(email="manager@example.com", password="s0meth1ng-good")
    return Team.objects.create(name="Managed Team", code="MNG", manager=manager)


def _rider(team, *, name: str, salary: int) -> Rider:
    return Rider.objects.create(
        name=name, team=team, weekly_salary=salary,
        climb=40, sprint=40, flat=40, resistance=40, positioning=40,
    )


def test_balance_is_zero_with_no_entries(db, team):
    assert balance_for(team) == 0


def test_balance_sums_signed_amounts(db, team):
    at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    LedgerEntry.objects.create(
        team=team, kind=LedgerEntry.Kind.STARTING_BALANCE, amount=500_000,
        occurred_at=at, description="Starting balance",
    )
    LedgerEntry.objects.create(
        team=team, kind=LedgerEntry.Kind.WAGES, amount=-14_400,
        occurred_at=at, description="Weekly wages",
    )

    assert balance_for(team) == 485_600


def test_ensure_opening_balance_is_idempotent(db, team):
    at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    first = ensure_opening_balance(team, at=at)
    second = ensure_opening_balance(team, at=at)

    assert first.pk == second.pk
    assert balance_for(team) == STARTING_BALANCE
    assert LedgerEntry.objects.filter(team=team).count() == 1


def test_ensure_opening_balance_stamps_game_time(db, team):
    at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)

    entry = ensure_opening_balance(team, at=at)

    assert entry.occurred_at == at


def test_reset_writes_the_difference(db, team):
    at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    LedgerEntry.objects.create(
        team=team, kind=LedgerEntry.Kind.STARTING_BALANCE, amount=STARTING_BALANCE,
        occurred_at=at, description="Starting balance",
    )
    LedgerEntry.objects.create(
        team=team, kind=LedgerEntry.Kind.WAGES, amount=-14_400,
        occurred_at=at, description="Weekly wages",
    )

    reset_to_starting_balance(team, at=at)

    # The prior entries must still exist — this is the append-only guarantee.
    assert entries_for(team).count() == 3
    assert balance_for(team) == STARTING_BALANCE


def test_reset_at_starting_balance_writes_nothing(db, team):
    at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    LedgerEntry.objects.create(
        team=team, kind=LedgerEntry.Kind.STARTING_BALANCE, amount=STARTING_BALANCE,
        occurred_at=at, description="Starting balance",
    )

    assert reset_to_starting_balance(team, at=at) is None
    assert LedgerEntry.objects.filter(team=team).count() == 1


def test_pay_race_prizes_writes_one_entry_per_placement(db, team, race):
    at = datetime(2027, 3, 2, 0, 0, tzinfo=dt_timezone.utc)
    prizes_by_team = {team.pk: [(2, 15_000), (5, 8_000)]}

    written = pay_race_prizes(
        race.pk, race_name=race.name, at=at, prizes_by_team=prizes_by_team
    )

    assert written == 2
    rows = list(LedgerEntry.objects.filter(team=team).order_by("position"))
    assert [row.position for row in rows] == [2, 5]
    assert [row.amount for row in rows] == [15_000, 8_000]
    assert all(row.kind == LedgerEntry.Kind.PRIZE_MONEY for row in rows)
    assert all(row.race_id == race.pk for row in rows)
    assert all(row.occurred_at == at for row in rows)
    assert all(row.description == f"Prize money — {race.name}" for row in rows)


def test_pay_race_prizes_is_idempotent(db, team, race):
    at = datetime(2027, 3, 2, 0, 0, tzinfo=dt_timezone.utc)
    prizes_by_team = {team.pk: [(2, 15_000), (5, 8_000)]}

    pay_race_prizes(race.pk, race_name=race.name, at=at, prizes_by_team=prizes_by_team)

    assert pay_race_prizes(
        race.pk, race_name=race.name, at=at, prizes_by_team=prizes_by_team
    ) == 0
    assert LedgerEntry.objects.filter(team=team).count() == 2


def test_pay_race_prizes_completes_a_partial_payout(db, team, race):
    at = datetime(2027, 3, 2, 0, 0, tzinfo=dt_timezone.utc)
    LedgerEntry.objects.create(
        team=team,
        kind=LedgerEntry.Kind.PRIZE_MONEY,
        amount=15_000,
        occurred_at=at,
        race=race,
        position=2,
        description=f"Prize money — {race.name}",
    )
    prizes_by_team = {team.pk: [(2, 15_000), (5, 8_000)]}

    written = pay_race_prizes(
        race.pk, race_name=race.name, at=at, prizes_by_team=prizes_by_team
    )

    assert written == 1
    rows = list(LedgerEntry.objects.filter(team=team).order_by("position"))
    assert [row.position for row in rows] == [2, 5]
    assert rows[0].amount == 15_000
    assert rows[1].amount == 8_000


def test_pay_gc_prizes_idempotent(db, team, race):
    at = datetime(2027, 3, 2, 0, 0, tzinfo=dt_timezone.utc)
    prizes_by_team = {team.pk: [(1, 40_000)]}

    first = pay_gc_prizes(
        race.pk, stage_race_name="Alpine Tour", at=at, prizes_by_team=prizes_by_team
    )
    second = pay_gc_prizes(
        race.pk, stage_race_name="Alpine Tour", at=at, prizes_by_team=prizes_by_team
    )

    assert first == 1
    assert second == 0
    rows = list(LedgerEntry.objects.filter(team=team, kind=LedgerEntry.Kind.GC_PRIZE_MONEY))
    assert len(rows) == 1
    assert rows[0].amount == 40_000
    assert rows[0].position == 1
    assert rows[0].race_id == race.pk
    assert rows[0].description == "General classification — Alpine Tour"


def test_gc_prize_and_stage_prize_same_team_race_position_both_recorded(db, team, race):
    # The final stage's own stage prize and its GC prize can land on the
    # same (team, race, position) — GC_PRIZE_MONEY must be a separate kind
    # from PRIZE_MONEY or one of the two writes silently no-ops against the
    # other's (team, race, position) constraint.
    at = datetime(2027, 3, 2, 0, 0, tzinfo=dt_timezone.utc)
    prizes_by_team = {team.pk: [(1, 10_000)]}
    gc_prizes_by_team = {team.pk: [(1, 40_000)]}

    stage_written = pay_race_prizes(
        race.pk, race_name=race.name, at=at, prizes_by_team=prizes_by_team
    )
    gc_written = pay_gc_prizes(
        race.pk, stage_race_name="Alpine Tour", at=at, prizes_by_team=gc_prizes_by_team
    )

    assert stage_written == 1
    assert gc_written == 1
    entries = LedgerEntry.objects.filter(team=team, race=race, position=1)
    assert entries.filter(kind=LedgerEntry.Kind.PRIZE_MONEY, amount=10_000).exists()
    assert entries.filter(kind=LedgerEntry.Kind.GC_PRIZE_MONEY, amount=40_000).exists()


def test_charge_transfer_fee_writes_a_debit(db, team):
    at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    ensure_opening_balance(team, at=at)

    charge_transfer_fee(team, amount=-37_000, at=at, description="Signed Somebody")

    entry = LedgerEntry.objects.get(team=team, kind=LedgerEntry.Kind.TRANSFER_FEE)
    assert entry.amount == -37_000
    assert entry.occurred_at == at
    assert entry.description == "Signed Somebody"
    assert entry.week_id is None
    assert balance_for(team) == STARTING_BALANCE - 37_000


def test_pay_transfer_income_writes_positive_transfer_fee_entry(db, team):
    at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    ensure_opening_balance(team, at=at)

    pay_transfer_income(team, amount=37_000, at=at, description="Sold Somebody at auction")

    entry = LedgerEntry.objects.get(team=team, kind=LedgerEntry.Kind.TRANSFER_FEE)
    assert entry.amount == 37_000
    assert entry.occurred_at == at
    assert entry.description == "Sold Somebody at auction"
    assert entry.week_id is None
    assert balance_for(team) == STARTING_BALANCE + 37_000


def test_write_salary_reviews_writes_one_per_managed_team(db, managed_team, season):
    rider = _rider(managed_team, name="Raised", salary=1200)
    changes = [{
        "rider_id": rider.pk, "rider_name": "Raised", "team_id": managed_team.pk,
        "from": 1000, "to": 1200,
    }]

    written = write_salary_reviews(season, changes)

    assert written == 1
    report = SalaryReviewReport.objects.get(team=managed_team, season=season)
    # `team_id` is dropped from the stored changes — it is report-grouping
    # data, not a per-rider fact.
    assert report.changes == [{"rider_id": rider.pk, "rider_name": "Raised", "from": 1000, "to": 1200}]
    assert report.payroll_before == 1000
    assert report.payroll_after == 1200


def test_write_salary_reviews_skips_unmanaged_teams(db, team, season):
    rider = _rider(team, name="Raised", salary=1200)
    changes = [{
        "rider_id": rider.pk, "rider_name": "Raised", "team_id": team.pk,
        "from": 1000, "to": 1200,
    }]

    written = write_salary_reviews(season, changes)

    assert written == 0
    assert SalaryReviewReport.objects.count() == 0


def test_write_salary_reviews_excludes_free_agent_changes(db, managed_team, season):
    _rider(managed_team, name="Rostered", salary=1000)
    changes = [{
        "rider_id": 999, "rider_name": "Free Agent", "team_id": None,
        "from": 500, "to": 800,
    }]

    write_salary_reviews(season, changes)

    # The team still gets a report (it has no qualifying change, so it is
    # empty and payroll is unchanged); the free agent appears in no report.
    report = SalaryReviewReport.objects.get(team=managed_team, season=season)
    assert report.changes == []
    assert report.payroll_before == 1000
    assert report.payroll_after == 1000


def test_write_salary_reviews_records_payroll_before_and_after(db, managed_team, season):
    raised = _rider(managed_team, name="Raised", salary=1500)
    cheaper = _rider(managed_team, name="Cheaper", salary=1000)
    changes = [
        {
            "rider_id": raised.pk, "rider_name": "Raised", "team_id": managed_team.pk,
            "from": 1400, "to": 1500,
        },
        {
            "rider_id": cheaper.pk, "rider_name": "Cheaper", "team_id": managed_team.pk,
            "from": 1200, "to": 1000,
        },
    ]

    write_salary_reviews(season, changes)

    report = SalaryReviewReport.objects.get(team=managed_team, season=season)
    assert report.payroll_after == 2500                  # 1500 + 1000
    assert report.payroll_before == 2600                 # net of the listed changes: +100 - 200
    assert len(report.changes) == 2


def test_write_salary_reviews_is_idempotent(db, managed_team, season):
    _rider(managed_team, name="Raised", salary=1200)
    changes = [{
        "rider_id": 7, "rider_name": "Raised", "team_id": managed_team.pk,
        "from": 1000, "to": 1200,
    }]

    wrote_first = write_salary_reviews(season, changes)
    wrote_second = write_salary_reviews(season, changes)

    # Load-bearing (plan D6): the second call's create() hits the (team,
    # season) constraint inside its own atomic(), so it is skipped — not
    # poisoned into a TransactionManagementError. Assert the row count, not
    # just the absence of an exception; a shared transaction wrapped around
    # the whole loop would also "not raise" on a single team.
    assert wrote_first == 1
    assert wrote_second == 0
    assert SalaryReviewReport.objects.filter(team=managed_team, season=season).count() == 1


def test_latest_salary_review_returns_newest_season(db, managed_team):
    earlier = datetime(2026, 3, 2, 0, 0, tzinfo=dt_timezone.utc)
    latest = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    first = Season.objects.create(number=1, starts_at=earlier)
    second = Season.objects.create(number=2, starts_at=latest)
    SalaryReviewReport.objects.create(
        team=managed_team, season=first, changes=[], payroll_before=1000, payroll_after=1000,
    )
    SalaryReviewReport.objects.create(
        team=managed_team, season=second, changes=[], payroll_before=1000, payroll_after=1000,
    )

    assert latest_salary_review(managed_team).season == second
