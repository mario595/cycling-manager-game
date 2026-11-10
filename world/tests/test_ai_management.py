"""The AI management's decision helpers, then its orchestrators.

The helpers are pure — rider and trainer lists in, answer out — so they are
tested with unsaved instances and no database. The orchestrators are
database-backed and are tested by what ends up in the staff slot and the
ledger.
"""

from __future__ import annotations

from riders.models import Rider
from staff.models import Trainer
from staff.pricing import hire_fee, weekly_salary
from world.ai_management import (
    AI_STAFF_RESERVE_WEEKS,
    can_afford_trainer,
    cheapest_trainer,
    dominant_attribute,
    focus_for_week,
)


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
