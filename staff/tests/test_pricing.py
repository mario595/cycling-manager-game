from __future__ import annotations

from staff.models import Trainer
from staff.pricing import FEE_WEEKS_OF_SALARY, hire_fee, weekly_salary


def _trainer(**skills) -> Trainer:
    """An in-memory Trainer (never saved) — pricing is pure arithmetic over
    the instance, so no DB is needed."""
    defaults = dict(name="Coach", climb=55, sprint=45, flat=60, resistance=50, positioning=40)
    defaults.update(skills)
    return Trainer(**defaults)


def test_salary_scales_with_speciality():
    low = _trainer(climb=70)
    high = _trainer(climb=95)

    assert weekly_salary(high) > weekly_salary(low)


def test_fee_is_twelve_weeks():
    trainer = _trainer(climb=90)

    assert hire_fee(trainer) == FEE_WEEKS_OF_SALARY * weekly_salary(trainer)


def test_price_reads_speciality_not_first_attribute():
    # The load-bearing test for Design decision 1's "read the speciality": a
    # sprint specialist and a climb specialist with the same peak must price
    # identically. A getattr(trainer, "climb") hardcode would price the
    # sprinter off their secondary skill, which is not the same number.
    sprinter = _trainer(climb=40, sprint=90, flat=60, resistance=55, positioning=50)
    climber = _trainer(climb=90, sprint=40, flat=60, resistance=55, positioning=50)

    assert weekly_salary(sprinter) == weekly_salary(climber)
    assert hire_fee(sprinter) == hire_fee(climber)


def test_prices_are_whole_credits():
    trainer = _trainer(climb=90)

    assert isinstance(weekly_salary(trainer), int)
    assert isinstance(hire_fee(trainer), int)