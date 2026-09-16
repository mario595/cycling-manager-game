from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

from accounts.models import User
from racing.models import Race, RaceResult
from riders.models import Rider
from teams.models import Team
from teams.services import ROSTER_SIZE, NoTeamAvailable, claim_team


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

    claimed = claim_team(user, name="New Name", code="NEW")

    assert claimed.pk == first.pk


def test_claim_renames_and_recodes(db, user, team):
    claimed = claim_team(user, name="Mountain Goats", code="MGO")

    assert claimed.pk == team.pk
    assert claimed.name == "Mountain Goats"
    assert claimed.code == "MGO"
    assert claimed.manager_id == user.pk


def test_claim_releases_old_riders_without_deleting(db, user, team, rider):
    claim_team(user, name="Mountain Goats", code="MGO")

    rider.refresh_from_db()
    assert rider.team_id is None
    assert Rider.objects.filter(pk=rider.pk).exists()


def test_claim_generates_a_full_roster(db, user, team, rider):
    claimed = claim_team(user, name="Mountain Goats", code="MGO")

    new_roster = claimed.riders.all()
    assert new_roster.count() == ROSTER_SIZE
    assert rider.pk not in set(new_roster.values_list("pk", flat=True))


def test_claim_raises_when_no_team_available(db, user):
    with pytest.raises(NoTeamAvailable):
        claim_team(user, name="Mountain Goats", code="MGO")


def test_claim_rejects_a_bad_code(db, user, team):
    with pytest.raises(ValidationError):
        claim_team(user, name="Mountain Goats", code="not-a-code")

    team.refresh_from_db()
    assert team.manager_id is None
    assert team.name != "Mountain Goats"


def test_claim_preserves_race_results(db, user, team, rider, race):
    result = RaceResult.objects.create(race=race, rider=rider, position=1, finish_time=100.0)

    claim_team(user, name="Mountain Goats", code="MGO")

    result.refresh_from_db()
    assert result.rider_id == rider.pk
