from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone

import pytest
from django.db import IntegrityError, transaction

from economy.models import (
    STARTING_BALANCE,
    WEEKLY_WAGE_PER_RIDER,
    FanbaseEntry,
    LedgerEntry,
    SponsorContract,
    SponsorOffer,
)
from schedule.models import Season, Week


@pytest.fixture
def season(db) -> Season:
    monday = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    return Season.objects.create(number=1, starts_at=monday)


@pytest.fixture
def week(season) -> Week:
    return Week.objects.create(
        season=season,
        number=1,
        starts_at=season.starts_at,
        ends_at=season.starts_at + timedelta(weeks=1),
    )


def test_ledger_entry_roundtrips(db, team):
    entry = LedgerEntry.objects.create(
        team=team,
        kind=LedgerEntry.Kind.STARTING_BALANCE,
        amount=STARTING_BALANCE,
        occurred_at=datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc),
        description="Starting balance",
    )

    entry.refresh_from_db()
    assert entry.team_id == team.pk
    assert entry.kind == LedgerEntry.Kind.STARTING_BALANCE
    assert entry.amount == STARTING_BALANCE
    assert entry.rider_count == 0
    assert entry.week_id is None
    assert entry.description == "Starting balance"


def test_wage_entries_are_unique_per_team_per_week(db, team, week):
    LedgerEntry.objects.create(
        team=team,
        kind=LedgerEntry.Kind.WAGES,
        amount=-(12 * WEEKLY_WAGE_PER_RIDER),
        occurred_at=week.starts_at,
        week=week,
        rider_count=12,
        description="Weekly wages",
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            LedgerEntry.objects.create(
                team=team,
                kind=LedgerEntry.Kind.WAGES,
                amount=-(12 * WEEKLY_WAGE_PER_RIDER),
                occurred_at=week.starts_at,
                week=week,
                rider_count=12,
                description="Weekly wages",
            )


def test_non_wage_entries_are_not_constrained(db, team):
    occurred_at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    LedgerEntry.objects.create(
        team=team,
        kind=LedgerEntry.Kind.TAKEOVER,
        amount=500_000,
        occurred_at=occurred_at,
        description="Team taken over",
    )
    LedgerEntry.objects.create(
        team=team,
        kind=LedgerEntry.Kind.TAKEOVER,
        amount=0,
        occurred_at=occurred_at,
        description="Team taken over",
    )

    assert LedgerEntry.objects.filter(team=team).count() == 2


def test_fanbase_entry_week_unique_per_team(db, team, week):
    FanbaseEntry.objects.create(
        team=team,
        kind=FanbaseEntry.Kind.WEEKLY,
        delta=250,
        occurred_at=week.starts_at,
        week=week,
        points=10,
        description="Weekly fanbase change",
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            FanbaseEntry.objects.create(
                team=team,
                kind=FanbaseEntry.Kind.WEEKLY,
                delta=250,
                occurred_at=week.starts_at,
                week=week,
                points=10,
                description="Weekly fanbase change",
            )


def test_fanbase_starting_and_takeover_rows_allow_null_week(db, team):
    occurred_at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    FanbaseEntry.objects.create(
        team=team,
        kind=FanbaseEntry.Kind.STARTING,
        delta=10_000,
        occurred_at=occurred_at,
        description="Starting fanbase",
    )
    FanbaseEntry.objects.create(
        team=team,
        kind=FanbaseEntry.Kind.TAKEOVER,
        delta=-20_000,
        occurred_at=occurred_at,
        description="Team taken over",
    )

    assert FanbaseEntry.objects.filter(team=team).count() == 2


def test_merchandise_entry_unique_per_team_per_week(db, team, week):
    LedgerEntry.objects.create(
        team=team,
        kind=LedgerEntry.Kind.MERCHANDISE,
        amount=400,
        occurred_at=week.starts_at,
        week=week,
        description="Merchandise revenue",
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            LedgerEntry.objects.create(
                team=team,
                kind=LedgerEntry.Kind.MERCHANDISE,
                amount=400,
                occurred_at=week.starts_at,
                week=week,
                description="Merchandise revenue",
            )


def test_wage_and_merchandise_entries_coexist_for_one_week(db, team, week):
    LedgerEntry.objects.create(
        team=team,
        kind=LedgerEntry.Kind.WAGES,
        amount=-(12 * WEEKLY_WAGE_PER_RIDER),
        occurred_at=week.starts_at,
        week=week,
        rider_count=12,
        description="Weekly wages",
    )
    LedgerEntry.objects.create(
        team=team,
        kind=LedgerEntry.Kind.MERCHANDISE,
        amount=400,
        occurred_at=week.starts_at,
        week=week,
        description="Merchandise revenue",
    )

    assert LedgerEntry.objects.filter(team=team, week=week).count() == 2


def _offer(team, season, *, profile="balanced", **overrides) -> SponsorOffer:
    defaults = dict(
        sponsor_name="Acme Cycles", weekly_base=5_000,
        floor_amount=3_000, ceiling_amount=8_000, sensitivity=0.5,
    )
    defaults.update(overrides)
    return SponsorOffer.objects.create(team=team, season=season, profile=profile, **defaults)


def _contract(team, season, *, profile="balanced", signed_at=None, **overrides) -> SponsorContract:
    defaults = dict(
        sponsor_name="Acme Cycles", weekly_base=5_000,
        floor_amount=3_000, ceiling_amount=8_000, sensitivity=0.5,
        signed_at=signed_at or datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc),
    )
    defaults.update(overrides)
    return SponsorContract.objects.create(team=team, season=season, profile=profile, **defaults)


def test_one_offer_per_profile_per_team_per_season(db, team, season):
    _offer(team, season, profile="balanced")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _offer(team, season, profile="balanced")


def test_offers_for_different_profiles_coexist(db, team, season):
    _offer(team, season, profile="steady")
    _offer(team, season, profile="balanced")
    _offer(team, season, profile="demanding")

    assert SponsorOffer.objects.filter(team=team, season=season).count() == 3


def test_one_active_contract_per_team_per_season(db, team, season):
    _contract(team, season)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            _contract(team, season)


def test_voided_contract_does_not_block_a_new_one(db, team, season):
    first = _contract(team, season)
    first.voided_at = datetime(2027, 3, 8, 0, 0, tzinfo=dt_timezone.utc)
    first.save(update_fields=["voided_at"])

    second = _contract(team, season)

    assert SponsorContract.objects.filter(team=team, season=season).count() == 2
    assert second.voided_at is None


def test_one_sponsorship_entry_per_team_per_week(db, team, week):
    LedgerEntry.objects.create(
        team=team,
        kind=LedgerEntry.Kind.SPONSORSHIP,
        amount=5_000,
        occurred_at=week.starts_at,
        week=week,
        description="Sponsorship",
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            LedgerEntry.objects.create(
                team=team,
                kind=LedgerEntry.Kind.SPONSORSHIP,
                amount=5_000,
                occurred_at=week.starts_at,
                week=week,
                description="Sponsorship",
            )


def test_one_trainer_salary_entry_per_team_per_week(db, team, week):
    LedgerEntry.objects.create(
        team=team,
        kind=LedgerEntry.Kind.TRAINER_SALARY,
        amount=-3_900,
        occurred_at=week.starts_at,
        week=week,
        description="Trainer salary",
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            LedgerEntry.objects.create(
                team=team,
                kind=LedgerEntry.Kind.TRAINER_SALARY,
                amount=-3_900,
                occurred_at=week.starts_at,
                week=week,
                description="Trainer salary",
            )


def test_several_trainer_fees_per_team_allowed(db, team):
    # The fee has no (team, week) constraint — a team can legitimately pay
    # several hire fees over a season. This is the one someone will
    # "helpfully" add by symmetry with the salary; the plan's W2 exists to
    # stop it.
    for at in (datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc),
               datetime(2027, 4, 1, 0, 0, tzinfo=dt_timezone.utc)):
        LedgerEntry.objects.create(
            team=team,
            kind=LedgerEntry.Kind.TRAINER_FEE,
            amount=-46_800,
            occurred_at=at,
            description="Trainer hire fee",
        )

    assert LedgerEntry.objects.filter(team=team, kind=LedgerEntry.Kind.TRAINER_FEE).count() == 2
