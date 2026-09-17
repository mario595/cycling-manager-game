from __future__ import annotations

from django.db import transaction

from .generation import TRAINERS_PER_SEASON_BOUNDARY, generate_trainer_pool
from .models import Trainer


class StaffError(Exception):
    """Base class for a staff change that cannot proceed."""


class TrainerNotAvailable(StaffError):
    """That trainer is not in the pool — hired by someone else, or never was."""


class SlotOccupied(StaffError):
    """The team already has a trainer; fire them first."""


class NoTrainerHired(StaffError):
    """The team has no trainer to fire."""


def hire_trainer(team, trainer_id: int) -> Trainer:
    """Move a pool trainer into `team`'s single slot.

    Locks the requested row for the duration, WITHOUT skip_locked: the
    caller asked for this specific trainer, so a contended row must make us
    wait and then report the truth, not silently behave as though the
    trainer never existed. See specs/trainers-as-hireable-staff-plan.md,
    Design decisions 3.
    """
    with transaction.atomic():
        try:
            trainer = Trainer.objects.select_for_update().get(pk=trainer_id)
        except Trainer.DoesNotExist:
            raise TrainerNotAvailable("That trainer is not available.")

        # Re-checked AFTER the lock, not before it. This is the line that
        # makes two simultaneous hires of the same trainer safe: the loser
        # of the race arrives here with team_id already set and is told so,
        # rather than overwriting the winner's hire.
        if trainer.team_id is not None:
            raise TrainerNotAvailable("That trainer has already been hired.")

        if Trainer.objects.filter(team=team).exists():
            raise SlotOccupied("Your team already has a trainer.")

        trainer.team = team
        trainer.save(update_fields=["team", "updated_at"])
    return trainer


def fire_trainer(team) -> Trainer:
    """Return `team`'s trainer to the shared pool. No cooldown, no penalty
    — the row survives and is immediately hireable by anyone, including
    this team again."""
    with transaction.atomic():
        trainer = Trainer.objects.select_for_update().filter(team=team).first()
        if trainer is None:
            raise NoTrainerHired("Your team has no trainer to fire.")
        trainer.team = None
        trainer.save(update_fields=["team", "updated_at"])
    return trainer


def trainer_for(team) -> Trainer | None:
    """`team`'s trainer, or None."""
    return Trainer.objects.filter(team=team).first()


def available_trainers():
    """The shared pool, as a queryset. Every unemployed trainer, visible to
    every team."""
    return Trainer.objects.filter(team__isnull=True)


def top_up_pool(*, count: int | None = None, rng=None) -> list[Trainer]:
    """Add `count` new trainers to the shared pool. Called once per crossed
    season boundary from world.services.tick(). Never deletes or trims:
    the pool only grows."""
    count = TRAINERS_PER_SEASON_BOUNDARY if count is None else count
    trainers = generate_trainer_pool(count, rng=rng)
    Trainer.objects.bulk_create(trainers)
    return trainers
