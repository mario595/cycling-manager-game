from __future__ import annotations

from datetime import timedelta

from django.core.management import call_command
from django.utils import timezone

from accounts.models import User
from economy.models import (
    STARTING_BALANCE,
    STARTING_FANBASE,
    FanbaseEntry,
    LedgerEntry,
    SponsorOffer,
)
from economy.services import balance_for, fanbase_for, offers_for
from riders.models import Rider
from schedule.models import Season
from teams.models import Team


def test_creates_unmanaged_teams_with_rosters(db):
    call_command("seed_teams", "--count=4", "--per-team=12")

    teams = Team.objects.all()
    assert teams.count() == 4
    assert all(t.manager_id is None for t in teams)
    for t in teams:
        assert t.riders.count() == 12
        for rider in t.riders.all():
            assert rider.attribute_snapshots.filter(week=None).count() == 1


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


def test_seeded_teams_have_an_opening_balance(db):
    call_command("seed_teams", "--count=4", "--per-team=12")

    for team in Team.objects.all():
        entry = LedgerEntry.objects.get(team=team, kind=LedgerEntry.Kind.STARTING_BALANCE)
        assert entry.amount == STARTING_BALANCE
        assert balance_for(team) == STARTING_BALANCE


def test_seed_teams_gives_every_team_a_starting_fanbase(db):
    call_command("seed_teams", "--count=4", "--per-team=12")

    for team in Team.objects.all():
        entry = FanbaseEntry.objects.get(team=team, kind=FanbaseEntry.Kind.STARTING)
        assert entry.delta == STARTING_FANBASE
        assert fanbase_for(team) == STARTING_FANBASE


def test_reseeding_does_not_double_credit(db):
    call_command("seed_teams", "--count=4", "--per-team=12")
    call_command("seed_teams", "--count=4", "--per-team=12")

    for team in Team.objects.all():
        opening_entries = LedgerEntry.objects.filter(
            team=team, kind=LedgerEntry.Kind.STARTING_BALANCE,
        )
        assert opening_entries.count() == 1
        assert balance_for(team) == STARTING_BALANCE


def test_reseeding_does_not_double_credit_fanbase(db):
    call_command("seed_teams", "--count=4", "--per-team=12")
    call_command("seed_teams", "--count=4", "--per-team=12")

    for team in Team.objects.all():
        starting_entries = FanbaseEntry.objects.filter(
            team=team, kind=FanbaseEntry.Kind.STARTING,
        )
        assert starting_entries.count() == 1
        assert fanbase_for(team) == STARTING_FANBASE


def test_claim_for_does_not_double_credit(db):
    user = User.objects.create_user(email="a@b.com", password="x", display_name="A")
    call_command("seed_teams", "--count=4", "--per-team=12", f"--claim-for={user.email}")

    claimed = Team.objects.get(manager=user)
    assert balance_for(claimed) == STARTING_BALANCE
    takeovers = LedgerEntry.objects.filter(
        team=claimed, kind=LedgerEntry.Kind.TAKEOVER,
    )
    assert takeovers.count() == 0  # claimed at exactly the starting balance


def test_seeding_before_a_season_exists_skips_offer_generation(db):
    # seed_teams normally runs before load_season (AGENTS.md's seeding
    # order) — a fresh world has no season yet, so there is nothing to
    # generate offers against.
    call_command("seed_teams", "--count=4", "--per-team=12")

    assert not SponsorOffer.objects.exists()


def test_seeded_teams_get_an_offer_round(db):
    # RealClock is active in tests without a MockClock override, so the
    # season must actually bracket real "now" for current_position() to
    # resolve it — start it a week ago rather than at an arbitrary date.
    monday = timezone.now().replace(
        hour=0, minute=0, second=0, microsecond=0,
    ) - timedelta(days=timezone.now().weekday(), weeks=1)
    season = Season.objects.create(number=1, starts_at=monday)

    call_command("seed_teams", "--count=4", "--per-team=12")

    for team in Team.objects.all():
        assert offers_for(team, season).count() == 3
