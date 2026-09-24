from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone

import pytest

from riders.models import Rider
from teams.models import Team
from transfers.pricing import severance_fee_for
from transfers.services import (
    InsufficientFunds,
    ROSTER_CAP,
    RiderNotAvailable,
    RiderNotOnRoster,
    RosterFull,
    free_agents,
    release_cost_for,
    release_rider,
    sign_free_agent,
)


def _rider(**overrides) -> Rider:
    """A persisted Rider — membership tests exercise `.team`, which an
    in-memory rider cannot carry."""
    defaults = dict(
        name="Test Rider",
        speciality=Rider.Speciality.ROULEUR,
        age=27,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    defaults.update(overrides)
    return Rider.objects.create(**defaults)


@pytest.fixture
def claimed_at():
    return datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)


def test_free_agents_returns_only_teamless_riders(db):
    team = Team.objects.create(name="Team Alpha", code="ALP")
    rostered = _rider(name="A Rostered", team=team)
    bob = _rider(name="Bob Free", team=None)
    alice = _rider(name="Alice Free", team=None)

    pool = list(free_agents())

    assert pool == [alice, bob]  # ordered by name
    assert rostered not in pool


def test_release_cost_is_zero_during_claim_cooldown(db, claimed_at):
    team = Team.objects.create(
        name="Team Alpha", code="ALP", managed_since=claimed_at,
    )
    rider = _rider(name="Claimed Rider", team=team, joined_team_at=claimed_at)

    # No in-season week has opened since the claim — the claim cooldown
    # holds, so the inherited roster releases for free (Design decision 2).
    assert release_cost_for(team, rider, weeks_opened=0) == 0


def test_release_cost_is_full_severance_after_cooldown_expires(db, claimed_at):
    team = Team.objects.create(
        name="Team Alpha", code="ALP", managed_since=claimed_at,
    )
    rider = _rider(name="Claimed Rider", team=team, joined_team_at=claimed_at)

    cost = release_cost_for(team, rider, weeks_opened=1)

    assert cost == severance_fee_for(rider)
    assert cost > 0


def test_release_cost_is_full_severance_for_a_signed_rider(db, claimed_at):
    team = Team.objects.create(
        name="Team Alpha", code="ALP", managed_since=claimed_at,
    )
    # Signed in two days after the claim: joined_team_at is a *different*
    # timestamp than managed_since, so even with weeks_opened=0 the
    # exemption must not apply (Design decision 2 — "assigned, not chosen").
    rider = _rider(
        name="Signed Rider", team=team,
        joined_team_at=claimed_at + timedelta(days=2),
    )

    assert release_cost_for(team, rider, weeks_opened=0) == severance_fee_for(rider)
    assert release_cost_for(team, rider, weeks_opened=0) > 0


def test_sign_free_agent_assigns_the_rider_and_stamps_joining(db, claimed_at):
    team = Team.objects.create(
        name="Team Alpha", code="ALP", managed_since=claimed_at,
    )
    free = _rider(name="Free Rider", team=None, unattached_since=claimed_at)

    signed = sign_free_agent(team, free.pk, at=claimed_at)

    signed.refresh_from_db()
    assert signed.team_id == team.pk
    assert signed.joined_team_at == claimed_at
    assert signed.unattached_since is None


def test_sign_free_agent_refuses_an_already_signed_rider(db, claimed_at):
    team = Team.objects.create(
        name="Team Alpha", code="ALP", managed_since=claimed_at,
    )
    taken = _rider(name="Taken Rider", team=team, joined_team_at=claimed_at)

    # The availability re-check happens UNDER the lock, proven sequentially
    # the same way staff/tests proves hire_trainer's: the row is mutated
    # before the call, so the post-lock check must refuse it.
    with pytest.raises(RiderNotAvailable):
        sign_free_agent(team, taken.pk, at=claimed_at)


def test_sign_free_agent_refuses_over_cap(db, claimed_at):
    team = Team.objects.create(
        name="Team Alpha", code="ALP", managed_since=claimed_at,
    )
    for i in range(ROSTER_CAP):
        _rider(name=f"Roster {i}", team=team)
    free = _rider(name="Free Rider", team=None)

    with pytest.raises(RosterFull):
        sign_free_agent(team, free.pk, at=claimed_at)

    free.refresh_from_db()
    assert free.team_id is None
    assert free.unattached_since is None


def test_sign_free_agent_raises_from_charge_and_rolls_back(db, claimed_at):
    # Load-bearing: the one place a bug would silently create a free rider
    # or a money-losing one. A raised InsufficientFunds inside the
    # transaction must leave team and stamp untouched.
    team = Team.objects.create(
        name="Team Alpha", code="ALP", managed_since=claimed_at,
    )
    free = _rider(name="Free Rider", team=None)

    def charge(rider, fee):
        raise InsufficientFunds("You cannot afford this rider's signing fee.")

    with pytest.raises(InsufficientFunds):
        sign_free_agent(team, free.pk, at=claimed_at, charge=charge)

    free.refresh_from_db()
    assert free.team_id is None
    assert free.joined_team_at is None
    assert free.unattached_since is None


def test_release_rider_sends_the_rider_to_the_pool_and_stamps_leaving(db, claimed_at):
    team = Team.objects.create(
        name="Team Alpha", code="ALP", managed_since=claimed_at,
    )
    rider = _rider(name="Mine", team=team, joined_team_at=claimed_at)

    released = release_rider(team, rider.pk, at=claimed_at, weeks_opened=1)

    released.refresh_from_db()
    assert released.team_id is None
    assert released.unattached_since == claimed_at
    assert released.joined_team_at == claimed_at  # untouched by a release


def test_release_rider_refuses_a_rider_not_on_the_team(db, claimed_at):
    team_a = Team.objects.create(
        name="Team Alpha", code="ALP", managed_since=claimed_at,
    )
    team_b = Team.objects.create(name="Team Bravo", code="BRA")
    rider = _rider(name="Not Yours", team=team_a, joined_team_at=claimed_at)

    with pytest.raises(RiderNotOnRoster):
        release_rider(team_b, rider.pk, at=claimed_at, weeks_opened=0)