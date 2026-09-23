from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone

import pytest

from riders.models import Rider
from teams.models import Team
from transfers.pricing import severance_fee_for
from transfers.services import free_agents, release_cost_for


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