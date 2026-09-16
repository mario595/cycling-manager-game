"""Generating trainers: one skill drawn high as the speciality, the other
four drawn from a lower, non-overlapping band.

See specs/trainers-as-hireable-staff-plan.md, Design decisions 5, for why
the bands must not overlap: it is what makes "exactly one skill is clearly
the highest" true by construction rather than by luck.
"""

from __future__ import annotations

import random

from riders.generation import FIRST_NAMES, LAST_NAMES
from riders.models import ENGINE_ATTRIBUTES, Rider

from .models import Trainer

#: The speciality skill is drawn from this band; the other four from
#: _OFF_SPECIALITY_BAND. The bands do not overlap — _OFF_SPECIALITY_BAND's
#: top (64) is strictly below _SPECIALITY_BAND's bottom (70) — which is
#: what makes "exactly one skill is clearly the highest" true by
#: construction rather than by luck. A gap of at least 6 stored points also
#: survives the 0-10 display scale: floor(70/10)=7 against floor(64/10)=6,
#: so the speciality reads as visibly higher on the bars the player
#: actually sees.
_SPECIALITY_BAND = (70, 95)

#: Never starts at 1. Weekly training (#36) requires off-speciality
#: training to always be worth something, so the floor is well clear of
#: zero. Load-bearing: dropping this floor toward 1 would let a trainer be
#: effectively useless in four of five skills, which the spec forbids.
_OFF_SPECIALITY_BAND = (25, 64)

#: New trainers added to the pool at each season boundary. Generous on
#: purpose — the spec says the pool must never be a scarcity constraint.
TRAINERS_PER_SEASON_BOUNDARY = 8

#: Size of the initial pool created by the seed_trainers command.
INITIAL_POOL_SIZE = 12


def _roll_name(nationality: str, rng: random.Random) -> str:
    first = rng.choice(FIRST_NAMES[nationality])
    last = rng.choice(LAST_NAMES[nationality])
    return f"{first} {last}"


def generate_trainer(
    *,
    speciality: str | None = None,
    nationality: str | None = None,
    rng: random.Random | None = None,
) -> Trainer:
    """Build an unsaved Trainer with exactly one clearly-highest skill.

    `speciality` must be one of ENGINE_ATTRIBUTES; omitted means rolled.
    Returns unsaved so callers can bulk_create.
    """
    rng = rng or random.Random()

    speciality = speciality or rng.choice(ENGINE_ATTRIBUTES)
    nationality = nationality or rng.choice(list(Rider.Nationality.values))

    skills = {
        name: (
            rng.randint(*_SPECIALITY_BAND)
            if name == speciality
            else rng.randint(*_OFF_SPECIALITY_BAND)
        )
        for name in ENGINE_ATTRIBUTES
    }

    return Trainer(
        name=_roll_name(nationality, rng),
        nationality=nationality,
        **skills,
    )


def generate_trainer_pool(
    size: int, *, rng: random.Random | None = None
) -> list[Trainer]:
    """`size` unsaved pool trainers (team left None).

    Specialities are spread deterministically rather than rolled
    independently: cycle through ENGINE_ATTRIBUTES so a pool cannot come
    out as, say, eight climb specialists. The spec promises a team "has a
    real choice" — five independent rolls do not guarantee that, and a pool
    with no sprint trainer in it is exactly the case a manager notices.
    """
    rng = rng or random.Random()
    return [
        generate_trainer(speciality=ENGINE_ATTRIBUTES[i % len(ENGINE_ATTRIBUTES)], rng=rng)
        for i in range(size)
    ]
