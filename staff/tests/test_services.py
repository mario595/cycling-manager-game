from __future__ import annotations

import pytest

from staff.generation import TRAINERS_PER_SEASON_BOUNDARY
from staff.models import Trainer
from staff.services import (
    NoTrainerHired,
    SlotOccupied,
    TrainerNotAvailable,
    available_trainers,
    fire_trainer,
    hire_trainer,
    top_up_pool,
)


def test_hire_fills_the_slot(trainer, team):
    hire_trainer(team, trainer.pk)

    trainer.refresh_from_db()
    assert trainer.team_id == team.pk
    assert trainer not in available_trainers()


def test_hire_a_trainer_already_hired_is_refused(trainer, team, other_team):
    hire_trainer(team, trainer.pk)

    with pytest.raises(TrainerNotAvailable):
        hire_trainer(other_team, trainer.pk)

    trainer.refresh_from_db()
    assert trainer.team_id == team.pk


def test_hire_when_slot_occupied_is_refused(trainer, team):
    hire_trainer(team, trainer.pk)
    second = Trainer.objects.create(
        name="Coach Two",
        climb=30,
        sprint=90,
        flat=45,
        resistance=50,
        positioning=35,
    )

    with pytest.raises(SlotOccupied):
        hire_trainer(team, second.pk)


def test_hire_unknown_id_is_refused(team):
    with pytest.raises(TrainerNotAvailable):
        hire_trainer(team, 999999)


def test_fire_returns_the_trainer_to_the_pool(trainer, team):
    hire_trainer(team, trainer.pk)

    fire_trainer(team)

    trainer.refresh_from_db()
    assert trainer.team is None
    assert trainer in available_trainers()


def test_fire_with_no_trainer_is_refused(team):
    with pytest.raises(NoTrainerHired):
        fire_trainer(team)


def test_fired_trainer_can_be_rehired_by_the_same_team(trainer, team):
    hire_trainer(team, trainer.pk)
    fire_trainer(team)

    hire_trainer(team, trainer.pk)

    trainer.refresh_from_db()
    assert trainer.team_id == team.pk


def test_top_up_only_adds(trainer, team):
    hire_trainer(team, trainer.pk)
    before_count = Trainer.objects.count()

    top_up_pool()

    assert Trainer.objects.count() == before_count + TRAINERS_PER_SEASON_BOUNDARY
    trainer.refresh_from_db()
    assert trainer.team_id == team.pk
