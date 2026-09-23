from __future__ import annotations

from datetime import datetime, timezone

import pytest
from django.core.exceptions import ValidationError

from accounts.models import User
from teams.models import ManagerialSpell, Team


def test_two_teams_may_share_a_code(db):
    Team.objects.create(name="Team Alpha", code="ARD")
    Team.objects.create(name="Team Beta", code="ARD")

    assert Team.objects.filter(code="ARD").count() == 2


@pytest.mark.parametrize("code", ["ard", "ARDE", "A1D"])
def test_code_must_be_three_uppercase_letters(db, code):
    team = Team(name="Team Gamma", code=code)
    with pytest.raises(ValidationError):
        team.full_clean()


def test_team_managed_since_defaults_to_null(db):
    team = Team.objects.create(name="Team Alpha", code="ARD")

    assert team.managed_since is None


def test_managerial_spell_orders_newest_first(db, team):
    user = User.objects.create_user(email="a@b.com", password="x", display_name="A")
    older = ManagerialSpell.objects.create(
        manager=user,
        team=team,
        team_name=team.name,
        team_code=team.code,
        ended_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        reason=ManagerialSpell.Reason.ADMIN,
    )
    newer = ManagerialSpell.objects.create(
        manager=user,
        team=team,
        team_name=team.name,
        team_code=team.code,
        ended_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
        reason=ManagerialSpell.Reason.ADMIN,
    )

    assert list(ManagerialSpell.objects.all()) == [newer, older]
