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
from riders.development_squad import open_squad
from riders.models import DevelopmentSquad, Rider
from schedule.models import Season
from staff.models import Trainer
from staff.services import focus_for, hire_trainer, set_focus, trainer_for
from teams.models import ManagerialSpell, Team
from teams.services import (
    ROSTER_SIZE,
    SQUAD_STRENGTH_DEPTH,
    NoTeamAvailable,
    _claim_candidates,
    claim_team,
    release_team,
    squad_strength,
)

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


def test_claim_breaks_a_strength_tie_by_lowest_pk(db, user):
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


def test_claim_gives_every_new_rider_a_baseline_snapshot(db, user, team):
    claimed = claim_team(user, name="Mountain Goats", code="MGO", at=AT)

    riders = list(claimed.riders.all())
    assert len(riders) == ROSTER_SIZE
    for rider in riders:
        assert rider.attribute_snapshots.filter(week=None).count() == 1


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


def test_claim_team_stamps_managed_since(db, user, team):
    claimed = claim_team(user, name="Mountain Goats", code="MGO", at=AT)

    assert claimed.managed_since == AT


def test_release_team_clears_manager_and_records_spell(db, user, team):
    claim_team(user, name="Mountain Goats", code="MGO", at=AT)
    team.refresh_from_db()
    released_at = datetime(2027, 4, 1, tzinfo=dt_timezone.utc)

    spell = release_team(team, reason=ManagerialSpell.Reason.ADMIN, at=released_at)

    team.refresh_from_db()
    assert team.manager_id is None
    assert team.managed_since is None
    assert spell.manager_id == user.pk
    assert spell.team_id == team.pk
    assert spell.team_name == "Mountain Goats"
    assert spell.team_code == "MGO"
    assert spell.started_at == AT
    assert spell.ended_at == released_at
    assert spell.reason == ManagerialSpell.Reason.ADMIN
    assert spell.acknowledged_at is None


def test_release_team_on_unmanaged_team_is_a_noop(db, team):
    result = release_team(team, reason=ManagerialSpell.Reason.ADMIN, at=AT)

    assert result is None
    assert ManagerialSpell.objects.count() == 0


def test_release_team_leaves_roster_and_ledger_untouched(db, user, team, rider):
    claim_team(user, name="Mountain Goats", code="MGO", at=AT)
    team.refresh_from_db()
    rider_count_before = team.riders.count()
    ledger_count_before = LedgerEntry.objects.filter(team=team).count()

    release_team(team, reason=ManagerialSpell.Reason.ADMIN, at=AT)

    assert team.riders.count() == rider_count_before
    assert LedgerEntry.objects.filter(team=team).count() == ledger_count_before


def test_release_team_tolerates_null_managed_since(db, user, team):
    team.manager = user
    team.save(update_fields=["manager"])

    spell = release_team(team, reason=ManagerialSpell.Reason.ADMIN, at=AT)

    assert spell.started_at is None


def test_released_team_can_be_claimed_again(db, user, team):
    other_user = User.objects.create_user(email="c@d.com", password="x", display_name="C")
    claim_team(user, name="Mountain Goats", code="MGO", at=AT)
    team.refresh_from_db()

    release_team(team, reason=ManagerialSpell.Reason.ADMIN, at=AT)

    reclaimed = claim_team(other_user, name="New Herd", code="NHD", at=AT)

    assert reclaimed.pk == team.pk
    assert reclaimed.manager_id == other_user.pk
    assert reclaimed.name == "New Herd"
    assert balance_for(reclaimed) == STARTING_BALANCE
    assert fanbase_for(reclaimed) == STARTING_FANBASE


def test_claim_closes_development_squad(db, user, team):
    """A claim is a takeover: the last manager's squad is not handed to the
    new one, who must open their own and pay their own fee. The row is
    deleted, so there is no fee to void and nothing to refund."""
    DevelopmentSquad.objects.create(team=team, level=3, opened_at=AT)

    claim_team(user, name="Mountain Goats", code="MGO", at=AT)

    assert not DevelopmentSquad.objects.filter(team=team).exists()


def test_claim_releases_graduates_and_discards_the_rest(db, user, team):
    """Closing a squad on claim (#33, #34) is not one blanket rule: a graduate
    has earned a market listing and lands in the pool with unattached_since
    stamped, while a rider still mid-development is discarded outright."""
    squad = DevelopmentSquad.objects.create(team=team, level=1, opened_at=AT)
    graduate = Rider.objects.create(
        name="Graduate One", development_squad=squad,
        intake_at=AT, graduated_at=AT,
        climb=20, sprint=20, flat=20, resistance=20, positioning=20,
    )
    in_development = Rider.objects.create(
        name="Youth One", development_squad=squad,
        climb=20, sprint=20, flat=20, resistance=20, positioning=20,
    )

    claim_team(user, name="Mountain Goats", code="MGO", at=AT)
    graduate.refresh_from_db()

    assert graduate.team_id is None
    assert graduate.development_squad_id is None
    assert graduate.unattached_since == AT
    assert not Rider.objects.filter(pk=in_development.pk).exists()


def test_claim_closes_the_squad_the_released_manager_bought(db, user, team, rider):
    """The squad only exists after a manager opened it, so the path a test
    with a bare DevelopmentSquad row skips: claim, open, release, claim."""
    claim_team(user, name="Mountain Goats", code="MGO", at=AT)
    open_squad(team, 1, at=AT)
    other_user = User.objects.create_user(email="c@d.com", password="x", display_name="C")
    release_team(team, reason=ManagerialSpell.Reason.ADMIN, at=AT)

    claim_team(other_user, name="New Herd", code="NHD", at=AT)

    assert not DevelopmentSquad.objects.filter(team=team).exists()


def test_release_keeps_development_squad(db, user, team):
    """Release is deliberately not claim's inverse (Design decision 9): a
    manager who quits leaves the team as it stands, squad included, and the
    claim that eventually follows is what clears it. Tested against a managed
    team, since an unmanaged one cannot have opened one."""
    claim_team(user, name="Mountain Goats", code="MGO", at=AT)
    open_squad(team, 1, at=AT)

    release_team(team, reason=ManagerialSpell.Reason.ADMIN, at=AT)

    assert DevelopmentSquad.objects.filter(team=team, level=1).exists()


def _trainer() -> Trainer:
    return Trainer.objects.create(
        name="Coach", climb=70, sprint=50, flat=50, resistance=50, positioning=50,
    )


def test_claim_keeps_the_ai_hired_trainer_and_voids_the_sponsor(db, user, team, season):
    # What the AI management (#45) leaves on an unmanaged team.
    trainer = hire_trainer(team, _trainer().pk)
    contract = sign_offer(team, ensure_offer_round(team, season, at=AT)[0].pk, at=AT)

    claim_team(user, name="Mountain Goats", code="MGO", at=AT)

    assert trainer_for(team) == trainer
    contract.refresh_from_db()
    assert contract.voided_at is not None
    assert active_contract(team, season) is None


def test_release_keeps_trainer_focus_and_sponsor(db, user, team, season):
    claim_team(user, name="Mountain Goats", code="MGO", at=AT)
    team.refresh_from_db()
    trainer = hire_trainer(team, _trainer().pk)
    set_focus(team, "sprint")
    contract = sign_offer(team, ensure_offer_round(team, season, at=AT)[0].pk, at=AT)

    release_team(team, reason=ManagerialSpell.Reason.ADMIN, at=AT)

    assert trainer_for(team) == trainer
    assert focus_for(team) == "sprint"
    assert active_contract(team, season) == contract


# --- #156: a claimed team keeps its riders --------------------------------


def _riders(team, n, level):
    """`n` saved rouleurs on `team`, every attribute at `level`."""
    return [
        Rider.objects.create(
            name=f"{team.code} {level} {i}", team=team,
            climb=level, sprint=level, flat=level, resistance=level, positioning=level,
        )
        for i in range(n)
    ]


def _unsaved(levels):
    return [
        Rider(climb=lv, sprint=lv, flat=lv, resistance=lv, positioning=lv)
        for lv in levels
    ]


def test_squad_strength_means_the_best_eight():
    riders = _unsaved([50] * 8 + [10, 10])
    assert squad_strength(riders) == pytest.approx(50)


def test_squad_strength_counts_missing_places_as_zero():
    riders = _unsaved([40, 40, 40])
    assert squad_strength(riders) == pytest.approx(40 * 3 / SQUAD_STRENGTH_DEPTH)


def test_claim_candidates_rank_by_distance_from_field_median(db, user):
    weak = Team.objects.create(name="Weak", code="WEK")
    middle = Team.objects.create(name="Middle", code="MID")
    strong = Team.objects.create(name="Strong", code="STR")
    managed = Team.objects.create(name="Managed", code="MAN", manager=user)
    _riders(weak, 8, 20)
    _riders(middle, 8, 50)
    _riders(strong, 8, 90)
    _riders(managed, 8, 70)  # median of 20, 50, 70, 90 is 60

    assert _claim_candidates() == [middle.pk, strong.pk, weak.pk]


def test_claim_candidates_break_ties_by_pk(db):
    first = Team.objects.create(name="First", code="FST")
    second = Team.objects.create(name="Second", code="SND")
    _riders(first, 8, 50)
    _riders(second, 8, 50)

    assert _claim_candidates() == [first.pk, second.pk]


def test_claim_hands_over_the_team_nearest_the_median(db, user):
    weak = Team.objects.create(name="Weak", code="WEK")
    middle = Team.objects.create(name="Middle", code="MID")
    strong = Team.objects.create(name="Strong", code="STR")
    _riders(weak, 12, 20)
    _riders(middle, 12, 50)
    _riders(strong, 12, 90)

    claimed = claim_team(user, name="Mountain Goats", code="MGO", at=AT)

    assert claimed.pk == middle.pk


def test_claim_skips_a_candidate_claimed_since_the_ranking(db, user, monkeypatch):
    taken = Team.objects.create(name="Taken", code="TKN")
    free = Team.objects.create(name="Free", code="FRE")
    other = User.objects.create_user(email="o@b.com", password="x", display_name="O")
    # The ranking was read while `taken` was free; it has been claimed since.
    monkeypatch.setattr("teams.services._claim_candidates", lambda: [taken.pk, free.pk])
    Team.objects.filter(pk=taken.pk).update(manager=other)

    claimed = claim_team(user, name="Mountain Goats", code="MGO", at=AT)

    assert claimed.pk == free.pk


def test_claim_keeps_the_teams_riders(db, user, team):
    originals = _riders(team, ROSTER_SIZE, 50)

    claimed = claim_team(user, name="Mountain Goats", code="MGO", at=AT)

    assert set(claimed.riders.values_list("pk", flat=True)) == {r.pk for r in originals}


def test_claim_tops_a_short_roster_up_to_twelve(db, user, team):
    originals = _riders(team, 3, 50)

    claimed = claim_team(user, name="Mountain Goats", code="MGO", at=AT)

    pks = set(claimed.riders.values_list("pk", flat=True))
    assert len(pks) == ROSTER_SIZE
    assert {r.pk for r in originals} <= pks


def test_claim_does_not_trim_a_large_roster(db, user, team):
    _riders(team, 14, 50)

    claimed = claim_team(user, name="Mountain Goats", code="MGO", at=AT)

    assert claimed.riders.count() == 14


def test_only_top_up_riders_get_a_baseline_snapshot(db, user, team):
    from riders.services import record_initial_snapshots

    originals = _riders(team, 3, 50)
    record_initial_snapshots(originals)

    claimed = claim_team(user, name="Mountain Goats", code="MGO", at=AT)

    for rider in claimed.riders.all():
        assert rider.attribute_snapshots.filter(week=None).count() == 1


def test_claim_stamps_inherited_riders_joined_team_at(db, user, team, rider):
    claimed = claim_team(user, name="Mountain Goats", code="MGO", at=AT)

    rider.refresh_from_db()
    assert rider.team_id == claimed.pk
    assert rider.unattached_since is None
    assert all(r.joined_team_at == claimed.managed_since == AT for r in claimed.riders.all())
