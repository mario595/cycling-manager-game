from __future__ import annotations

import random

from riders.display import to_display_scale
from riders.models import ENGINE_ATTRIBUTES

from staff.generation import (
    _OFF_SPECIALITY_BAND,
    generate_trainer,
    generate_trainer_pool,
)


def test_exactly_one_skill_is_highest():
    rng = random.Random(1)
    for _ in range(200):
        trainer = generate_trainer(rng=rng)
        skills = [getattr(trainer, name) for name in ENGINE_ATTRIBUTES]
        assert skills.count(max(skills)) == 1


def test_speciality_is_clearly_higher_on_the_display_scale():
    rng = random.Random(2)
    for _ in range(200):
        trainer = generate_trainer(rng=rng)
        speciality_display = to_display_scale(getattr(trainer, trainer.speciality))
        for name in ENGINE_ATTRIBUTES:
            if name == trainer.speciality:
                continue
            assert speciality_display > to_display_scale(getattr(trainer, name))


def test_no_skill_sits_at_the_floor():
    rng = random.Random(3)
    for _ in range(200):
        trainer = generate_trainer(rng=rng)
        for name in ENGINE_ATTRIBUTES:
            assert getattr(trainer, name) >= _OFF_SPECIALITY_BAND[0]


def test_requested_speciality_is_honoured():
    trainer = generate_trainer(speciality="sprint", rng=random.Random(4))
    assert trainer.speciality == "sprint"


def test_generation_is_deterministic_for_a_seed():
    first = generate_trainer(rng=random.Random(7))
    second = generate_trainer(rng=random.Random(7))

    assert first.name == second.name
    assert first.nationality == second.nationality
    for name in ENGINE_ATTRIBUTES:
        assert getattr(first, name) == getattr(second, name)


def test_pool_covers_every_speciality():
    pool = generate_trainer_pool(10, rng=random.Random(5))
    assert {trainer.speciality for trainer in pool} == set(ENGINE_ATTRIBUTES)


def test_generated_trainers_are_unsaved():
    trainer = generate_trainer(rng=random.Random(6))
    assert trainer.pk is None
