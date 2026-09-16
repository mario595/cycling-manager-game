from __future__ import annotations

from django.core.management import call_command

from accounts.models import User
from riders.models import Rider
from teams.models import Team


def test_creates_unmanaged_teams_with_rosters(db):
    call_command("seed_teams", "--count=4", "--per-team=12")

    teams = Team.objects.all()
    assert teams.count() == 4
    assert all(t.manager_id is None for t in teams)
    for t in teams:
        assert t.riders.count() == 12


def test_reset_leaves_managed_teams_alone(db):
    user = User.objects.create_user(email="a@b.com", password="x", display_name="A")
    managed = Team.objects.create(name="Managed Team", code="MGT", manager=user)
    Rider.objects.create(
        name="Managed Rider", team=managed,
        climb=60, sprint=60, flat=60, resistance=60, positioning=60,
    )

    call_command("seed_teams", "--count=2", "--per-team=12", "--reset")

    managed.refresh_from_db()
    assert managed.manager_id == user.pk
    assert managed.riders.count() == 1
    assert Team.objects.filter(manager__isnull=True).count() == 2


def test_reset_deletes_only_unmanaged_teams_and_riders(db):
    call_command("seed_teams", "--count=3", "--per-team=12")
    assert Team.objects.count() == 3

    call_command("seed_teams", "--count=2", "--per-team=12", "--reset")

    assert Team.objects.count() == 2
    assert Rider.objects.count() == 24  # 2 teams * 12


def test_codes_are_three_uppercase_letters(db):
    call_command("seed_teams", "--count=20", "--per-team=1")

    for team in Team.objects.all():
        team.full_clean(exclude=["manager"])
