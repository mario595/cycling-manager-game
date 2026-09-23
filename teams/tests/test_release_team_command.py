from __future__ import annotations

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from accounts.models import User
from teams.models import ManagerialSpell, Team


def _claimed_team() -> Team:
    user = User.objects.create_user(email="a@b.com", password="x", display_name="A")
    return Team.objects.create(name="Mountain Goats", code="MGO", manager=user)


def test_releases_by_id(db):
    team = _claimed_team()

    call_command("release_team", str(team.pk))

    team.refresh_from_db()
    assert team.manager_id is None
    spell = ManagerialSpell.objects.get(team=team)
    assert spell.reason == ManagerialSpell.Reason.ADMIN


def test_releases_by_name(db):
    team = _claimed_team()

    call_command("release_team", "Mountain Goats", "--reason=inactivity")

    team.refresh_from_db()
    assert team.manager_id is None
    spell = ManagerialSpell.objects.get(team=team)
    assert spell.reason == ManagerialSpell.Reason.INACTIVITY


def test_unknown_team_raises_command_error(db):
    with pytest.raises(CommandError):
        call_command("release_team", "Nonexistent Team")


def test_unmanaged_team_raises_command_error(db):
    team = Team.objects.create(name="Free Team", code="FRE")

    with pytest.raises(CommandError):
        call_command("release_team", str(team.pk))
