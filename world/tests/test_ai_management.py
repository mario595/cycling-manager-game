"""The AI management's decision helpers, then its orchestrators.

The helpers are pure — rider and trainer lists in, answer out — so they are
tested with unsaved instances and no database. The orchestrators are
database-backed and are tested by what ends up in the staff slot and the
ledger.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone

import pytest

from accounts.models import User
from economy.models import STARTING_BALANCE, LedgerEntry, SponsorContract, SponsorOffer
from economy.services import (
    active_contract,
    ensure_offer_round,
    ensure_opening_balance,
    ensure_starting_fanbase,
    sign_offer,
    void_sponsorship,
)
from riders.models import Rider
from staff.models import Trainer
from staff.pricing import hire_fee, weekly_salary
from schedule.models import Season, Week
from staff.models import TrainingFocus
from staff.services import focus_for, trainer_for
from teams.models import Team
from world import ai_management
from world.ai_management import (
    AI_STAFF_RESERVE_WEEKS,
    can_afford_trainer,
    cheapest_trainer,
    dominant_attribute,
    focus_for_week,
    hire_ai_trainers,
    set_ai_focuses,
    sign_ai_sponsors,
)
from world.services import now


def _rider(pk: int, speciality: str) -> Rider:
    return Rider(pk=pk, name=f"Rider {pk}", speciality=speciality)


def _trainer(pk: int, score: int) -> Trainer:
    """An unsaved trainer whose speciality (climb) scores `score`, which is
    what sets their price."""
    return Trainer(
        pk=pk, name=f"Trainer {pk}",
        climb=score, sprint=50, flat=50, resistance=50, positioning=50,
    )


def test_dominant_attribute_per_speciality():
    assert dominant_attribute(Rider.Speciality.CLIMBER) == "climb"
    assert dominant_attribute(Rider.Speciality.SPRINTER) == "sprint"
    assert dominant_attribute(Rider.Speciality.ROULEUR) == "flat"
    assert dominant_attribute(Rider.Speciality.PUNCHEUR) == "climb"
    assert dominant_attribute(Rider.Speciality.DOMESTIQUE) == "resistance"


def test_focus_rotation_is_weighted_by_the_roster():
    roster = [
        _rider(1, Rider.Speciality.CLIMBER),
        _rider(2, Rider.Speciality.CLIMBER),
        _rider(3, Rider.Speciality.SPRINTER),
        _rider(4, Rider.Speciality.CLIMBER),
    ]

    focuses = [focus_for_week(roster, week, team_pk=7) for week in range(1, 5)]

    assert sorted(focuses) == ["climb", "climb", "climb", "sprint"]


def test_focus_is_deterministic_whatever_order_the_roster_comes_in():
    roster = [
        _rider(3, Rider.Speciality.SPRINTER),
        _rider(1, Rider.Speciality.CLIMBER),
        _rider(2, Rider.Speciality.DOMESTIQUE),
    ]

    for week in range(1, 13):
        assert focus_for_week(roster, week, 5) == focus_for_week(list(reversed(roster)), week, 5)


def test_focus_for_an_empty_roster_is_none():
    assert focus_for_week([], 3, 1) is None


def test_cheapest_trainer_breaks_a_fee_tie_by_pk():
    pricey = _trainer(1, 95)
    tied_high_pk = _trainer(3, 70)
    tied_low_pk = _trainer(2, 70)

    assert cheapest_trainer([pricey, tied_high_pk, tied_low_pk]) is tied_low_pk


def test_cheapest_trainer_of_an_empty_pool_is_none():
    assert cheapest_trainer([]) is None


def test_can_afford_trainer_at_the_boundary():
    trainer = _trainer(1, 70)
    payroll = 14_000
    exact = hire_fee(trainer) + AI_STAFF_RESERVE_WEEKS * (payroll + weekly_salary(trainer))

    assert can_afford_trainer(exact, payroll, trainer)
    assert not can_afford_trainer(exact - 1, payroll, trainer)


def _team(code: str, *, balance: int = STARTING_BALANCE, manager: User | None = None) -> Team:
    team = Team.objects.create(name=f"Team {code}", code=code, manager=manager)
    ensure_opening_balance(team, at=now())
    ensure_starting_fanbase(team, at=now())
    if balance != STARTING_BALANCE:
        _adjust(team, balance - STARTING_BALANCE)
    return team


def _adjust(team: Team, amount: int) -> None:
    LedgerEntry.objects.create(
        team=team, kind=LedgerEntry.Kind.WAGES, amount=amount,
        occurred_at=now(), description="Weekly wages",
    )


def _human(code: str) -> User:
    return User.objects.create_user(email=f"{code.lower()}@example.com", password="s0meth1ng-good")


def _pool_trainer(name: str, score: int) -> Trainer:
    return Trainer.objects.create(
        name=name, climb=score, sprint=50, flat=50, resistance=50, positioning=50,
    )


def _fees(team: Team) -> list[int]:
    return list(
        LedgerEntry.objects.filter(team=team, kind=LedgerEntry.Kind.TRAINER_FEE)
        .values_list("amount", flat=True)
    )


def test_funded_unmanaged_team_hires_the_cheapest_trainer(db):
    team = _team("AIA")
    _pool_trainer("Expensive", 95)
    cheap = _pool_trainer("Cheap", 70)

    hired, error = hire_ai_trainers(now())

    assert (hired, error) == (1, "")
    assert trainer_for(team) == cheap
    assert _fees(team) == [-hire_fee(cheap)]


def test_managed_team_never_hires(db):
    team = _team("HUM", manager=_human("HUM"))
    _pool_trainer("Cheap", 70)

    assert hire_ai_trainers(now()) == (0, "")
    assert trainer_for(team) is None
    assert _fees(team) == []


def test_unaffordable_hire_is_skipped_and_retried_later(db):
    trainer = _pool_trainer("Cheap", 70)
    needed = hire_fee(trainer) + AI_STAFF_RESERVE_WEEKS * weekly_salary(trainer)
    team = _team("AIA", balance=needed - 1)

    assert hire_ai_trainers(now()) == (0, "")
    assert trainer_for(team) is None
    assert _fees(team) == []

    _adjust(team, 1)

    assert hire_ai_trainers(now()) == (1, "")
    assert trainer_for(team) == trainer


def test_one_trainer_two_teams_goes_to_the_lower_pk(db):
    first = _team("AIA")
    second = _team("AIB")
    _pool_trainer("Only", 70)

    assert hire_ai_trainers(now()) == (1, "")
    assert trainer_for(first) is not None
    assert trainer_for(second) is None


def test_hiring_twice_neither_hires_nor_charges_again(db):
    team = _team("AIA")
    _pool_trainer("Cheap", 70)
    _pool_trainer("Cheaper still", 70)

    hire_ai_trainers(now())
    assert hire_ai_trainers(now()) == (0, "")

    assert Trainer.objects.filter(team=team).count() == 1
    assert len(_fees(team)) == 1


def test_trainer_taken_by_a_human_since_the_pool_was_read_is_skipped(db, monkeypatch):
    ai_team = _team("AIA")
    human_team = _team("HUM", manager=_human("HUM"))
    taken = _pool_trainer("Taken", 70)
    stale_pool = [taken]
    taken.team = human_team
    taken.save()
    monkeypatch.setattr(ai_management, "available_trainers", lambda: stale_pool)

    assert hire_ai_trainers(now()) == (0, "")
    assert trainer_for(ai_team) is None
    assert _fees(ai_team) == []


@pytest.fixture
def season(db) -> Season:
    return Season.objects.create(
        number=1,
        starts_at=datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc),
    )


@pytest.fixture
def week(season) -> Week:
    return Week.objects.create(
        season=season,
        number=1,
        starts_at=season.starts_at,
        ends_at=season.starts_at + timedelta(weeks=1),
    )


def _sprinters(team: Team, count: int = 4) -> list[Rider]:
    return [
        Rider.objects.create(
            name=f"{team.code} Sprinter {i}", team=team, speciality=Rider.Speciality.SPRINTER,
            climb=40, sprint=70, flat=50, resistance=40, positioning=50,
        )
        for i in range(count)
    ]


def _staffed(team: Team, name: str = "Coach") -> Trainer:
    trainer = _pool_trainer(name, 70)
    trainer.team = team
    trainer.save()
    return trainer


def test_set_ai_focuses_sets_unmanaged_teams_focus_once_per_week(db, week):
    team = _team("AIA")
    _sprinters(team)
    _staffed(team)

    assert set_ai_focuses(week) == 1
    assert focus_for(team) == "sprint"
    assert set_ai_focuses(week) == 0
    assert focus_for(team) == "sprint"


def test_set_ai_focuses_leaves_a_team_with_no_trainer_alone(db, week):
    team = _team("AIA")
    _sprinters(team)

    assert set_ai_focuses(week) == 0
    assert not TrainingFocus.objects.filter(team=team).exists()


def test_set_ai_focuses_never_touches_a_managed_team(db, week):
    team = _team("HUM", manager=_human("HUM"))
    _sprinters(team)
    _staffed(team)

    assert set_ai_focuses(week) == 0
    assert not TrainingFocus.objects.filter(team=team).exists()


def test_sign_ai_sponsors_signs_the_steady_offer_once(db, season):
    team = _team("AIA")

    assert sign_ai_sponsors(season, now()) == (1, "")
    contract = active_contract(team, season)
    assert contract.profile == "steady"
    assert sign_ai_sponsors(season, now()) == (0, "")
    assert SponsorContract.objects.filter(team=team).count() == 1


def test_sign_ai_sponsors_keeps_an_existing_contract(db, season):
    team = _team("AIA")
    ensure_offer_round(team, season, at=now())
    balanced = SponsorOffer.objects.get(team=team, season=season, profile="balanced")
    sign_offer(team, balanced.pk, at=now())

    assert sign_ai_sponsors(season, now()) == (0, "")
    assert active_contract(team, season).profile == "balanced"


def test_sign_ai_sponsors_gives_a_cleared_team_a_fresh_round_and_signs_it(db, season):
    team = _team("AIA")
    ensure_offer_round(team, season, at=now())
    sign_offer(team, SponsorOffer.objects.get(team=team, season=season, profile="demanding").pk, at=now())
    # What a claim does; the team is then released back to the AI.
    void_sponsorship(team, at=now())

    assert sign_ai_sponsors(season, now()) == (1, "")
    assert active_contract(team, season).profile == "steady"


def test_sign_ai_sponsors_never_touches_a_managed_team(db, season):
    team = _team("HUM", manager=_human("HUM"))

    assert sign_ai_sponsors(season, now()) == (0, "")
    assert active_contract(team, season) is None
    assert not SponsorOffer.objects.filter(team=team).exists()
