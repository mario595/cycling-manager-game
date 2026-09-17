from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from staff.models import Trainer


def test_pool_trainer_has_no_team(trainer):
    assert trainer.team is None


def test_speciality_is_the_highest_skill(trainer):
    assert trainer.speciality == "climb"


def test_a_team_cannot_have_two_trainers(trainer, team):
    trainer.team = team
    trainer.save()

    second = Trainer(
        name="Coach Two",
        climb=30,
        sprint=90,
        flat=45,
        resistance=50,
        positioning=35,
    )
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            second.team = team
            second.save()


def test_skill_below_one_is_rejected(trainer):
    trainer.climb = 0
    with pytest.raises(ValidationError):
        trainer.full_clean()


def test_skill_above_100_is_rejected(trainer):
    trainer.climb = 101
    with pytest.raises(ValidationError):
        trainer.full_clean()
