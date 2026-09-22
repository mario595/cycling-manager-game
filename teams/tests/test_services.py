from __future__ import annotations

from datetime import datetime, timezone as dt_timezone

import pytest
from django.core.exceptions import ValidationError

from accounts.models import User
from economy.models import STARTING_BALANCE, STARTING_FANBASE, FanbaseEntry, LedgerEntry
from economy.services import (
    active_contract,
    balance_for,
    ensure_offer_round,
    entries_for,
    fanbase_entries_for,
    fanbase_for,
    offers_for,
    sign_offer,
)
from racing.models import Race, RaceResult
from riders.models import Rider
from schedule.models import Season
from teams.models import Team
from teams.services import ROSTER_SIZE, NoTeamAvailable, claim_team

#: Game time the takeover entries under test are stamped with. claim_team
#: requires it so library code never reads the clock itself (AGENTS.md) —
#: the caller supplies world.services.now(). Tests pass a fixed moment.
AT = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)


@pytest.fixture
def user(db) -> User:
    return User.objects.create_user(email="a@b.com", password="x", display_name="A")


@pytest.fixture
def race(db) -> Race:
    return Race.objects.create(
        name="Old Race",
        course=[{"length": 500.0, "gradient": 0.0}],
        status=Race.Status.FINISHED,
    )


def test_claim_assigns_lowest_pk_unmanaged_team(db, user):
    first = Team.objects.create(name="Team Alpha", code="ALP")
    Team.objects.create(name="Team Beta", code="BET")

    claimed = claim_team(user, name="New Name", code="NEW", at=AT)

    assert claimed.pk == first.pk


def test_claim_renames_and_recodes(db, user, team):
    claimed = claim_team(user, name="Mountain Goats", code="MGO", at=AT)

    assert claimed.pk == team.pk
    assert claimed.name == "Mountain Goats"
    assert claimed.code == "MGO"
    assert claimed.manager_id == user.pk


def test_claim_releases_old_riders_without_deleting(db, user, team, rider):
    claim_team(user, name="Mountain Goats", code="MGO", at=AT)

    rider.refresh_from_db()
    assert rider.team_id is None
    assert Rider.objects.filter(pk=rider.pk).exists()


def test_claim_generates_a_full_roster(db, user, team, rider):
    claimed = claim_team(user, name="Mountain Goats", code="MGO", at=AT)

    new_roster = claimed.riders.all()
    assert new_roster.count() == ROSTER_SIZE
    assert rider.pk not in set(new_roster.values_list("pk", flat=True))


def test_claim_raises_when_no_team_available(db, user):
    with pytest.raises(NoTeamAvailable):
        claim_team(user, name="Mountain Goats", code="MGO", at=AT)


def test_claim_rejects_a_bad_code(db, user, team):
    with pytest.raises(ValidationError):
        claim_team(user, name="Mountain Goats", code="not-a-code", at=AT)

    team.refresh_from_db()
    assert team.manager_id is None
    assert team.name != "Mountain Goats"


def test_claim_preserves_race_results(db, user, team, rider, race):
    result = RaceResult.objects.create(race=race, rider=rider, position=1, finish_time=100.0)

    claim_team(user, name="Mountain Goats", code="MGO", at=AT)

    result.refresh_from_db()
    assert result.rider_id == rider.pk


def test_claim_resets_balance_to_starting_amount(db, user, team):
    at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    LedgerEntry.objects.create(
        team=team, kind=LedgerEntry.Kind.STARTING_BALANCE, amount=STARTING_BALANCE,
        occurred_at=at, description="Starting balance",
    )
    LedgerEntry.objects.create(
        team=team, kind=LedgerEntry.Kind.WAGES, amount=-14_400,
        occurred_at=at, description="Weekly wages",
    )

    claim_team(user, name="Mountain Goats", code="MGO", at=AT)

    assert balance_for(team) == STARTING_BALANCE


def test_claim_preserves_prior_ledger_entries(db, user, team):
    at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    original = LedgerEntry.objects.create(
        team=team, kind=LedgerEntry.Kind.STARTING_BALANCE, amount=STARTING_BALANCE,
        occurred_at=at, description="Starting balance",
    )
    LedgerEntry.objects.create(
        team=team, kind=LedgerEntry.Kind.WAGES, amount=-14_400,
        occurred_at=at, description="Weekly wages",
    )

    claim_team(user, name="Mountain Goats", code="MGO", at=AT)

    entries = list(entries_for(team))
    assert any(e.pk == original.pk for e in entries)
    assert any(e.kind == LedgerEntry.Kind.TAKEOVER for e in entries)


def test_claiming_a_team_resets_its_fanbase(db, user, team):
    at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    FanbaseEntry.objects.create(
        team=team, kind=FanbaseEntry.Kind.STARTING, delta=STARTING_FANBASE,
        occurred_at=at, description="Starting fanbase",
    )
    FanbaseEntry.objects.create(
        team=team, kind=FanbaseEntry.Kind.WEEKLY, delta=20_000,
        occurred_at=at, description="Weekly fanbase change",
    )

    claim_team(user, name="Mountain Goats", code="MGO", at=AT)

    assert fanbase_for(team) == STARTING_FANBASE


def test_claim_preserves_prior_fanbase_entries(db, user, team):
    at = datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)
    original = FanbaseEntry.objects.create(
        team=team, kind=FanbaseEntry.Kind.STARTING, delta=STARTING_FANBASE,
        occurred_at=at, description="Starting fanbase",
    )
    FanbaseEntry.objects.create(
        team=team, kind=FanbaseEntry.Kind.WEEKLY, delta=20_000,
        occurred_at=at, description="Weekly fanbase change",
    )

    claim_team(user, name="Mountain Goats", code="MGO", at=AT)

    entries = list(fanbase_entries_for(team))
    assert any(e.pk == original.pk for e in entries)
    assert any(e.kind == FanbaseEntry.Kind.TAKEOVER for e in entries)


@pytest.fixture
def season(db) -> Season:
    return Season.objects.create(number=1, starts_at=AT)


def test_claiming_voids_the_previous_contract(db, user, team, season):
    offers = ensure_offer_round(team, season, at=AT)
    contract = sign_offer(team, offers[0].pk, at=AT)

    claim_team(user, name="Mountain Goats", code="MGO", at=AT)

    contract.refresh_from_db()
    assert contract.voided_at is not None
    assert active_contract(team, season) is None


def test_claiming_clears_unsigned_offers(db, user, team, season):
    ensure_offer_round(team, season, at=AT)

    claim_team(user, name="Mountain Goats", code="MGO", at=AT)

    assert offers_for(team, season).count() == 0
