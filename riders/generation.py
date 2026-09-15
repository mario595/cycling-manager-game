"""Generating riders: a speciality first, then a build and five attributes
consistent with it, plus the hidden traits that will govern their future.

See specs/rider-attributes.md and specs/rider-attributes-plan.md, *Design
decisions* 6-8, for why generation is seeded/deterministic and why
speciality is chosen before attributes rather than the reverse.
"""

from __future__ import annotations

import random

from .models import ENGINE_ATTRIBUTES, Rider

#: Per-speciality attribute weighting. 1.0 means "this rider's quality,
#: unmodified"; below 1.0 means "weaker than their quality in this attribute".
#: Each row sums to ~5.0 so no speciality is globally stronger than another —
#: only differently shaped. Load-bearing: if one row sums higher, that
#: speciality's riders win races for no reason the player can see.
SPECIALITY_PROFILES: dict[str, dict[str, float]] = {
    Rider.Speciality.CLIMBER: {
        "climb": 1.45, "sprint": 0.55, "flat": 0.80, "resistance": 1.10, "positioning": 1.10,
    },
    Rider.Speciality.SPRINTER: {
        "climb": 0.55, "sprint": 1.45, "flat": 1.10, "resistance": 0.80, "positioning": 1.10,
    },
    Rider.Speciality.ROULEUR: {
        "climb": 0.85, "sprint": 0.85, "flat": 1.30, "resistance": 1.10, "positioning": 0.90,
    },
    Rider.Speciality.PUNCHEUR: {
        "climb": 1.15, "sprint": 1.05, "flat": 0.85, "resistance": 0.85, "positioning": 1.10,
    },
    Rider.Speciality.DOMESTIQUE: {
        "climb": 0.80, "sprint": 0.70, "flat": 1.05, "resistance": 1.35, "positioning": 1.10,
    },
}

#: Per-speciality (height_cm, weight_kg) means a generated rider's build is
#: drawn around. Climbers light and short, sprinters heavy and tall — spec
#: item 4.
BUILD_PROFILES: dict[str, tuple[int, int]] = {
    Rider.Speciality.CLIMBER: (170, 60),
    Rider.Speciality.SPRINTER: (185, 80),
    Rider.Speciality.ROULEUR: (180, 72),
    Rider.Speciality.PUNCHEUR: (176, 68),
    Rider.Speciality.DOMESTIQUE: (181, 74),
}

#: Quality levels drawn for a generated roster, as (weight, low, high).
#: Skewed so most riders are unremarkable: a spread, not a bell curve
#: centred on "good" — the property spec item 11 and #46 depend on.
QUALITY_SPREAD: list[tuple[int, int, int]] = [
    (15, 20, 40),   # clearly not worth keeping
    (55, 41, 65),   # most of a roster: unremarkable
    (25, 66, 82),   # clearly worth building around
    (5, 83, 95),    # a standout
]

#: First/last name pools, per nationality. Only Spain exists today; adding a
#: second nationality is a new key in each dict, not a code change — see
#: Rider.Nationality.
FIRST_NAMES: dict[str, list[str]] = {
    Rider.Nationality.SPAIN: [
        "Alejandro", "Carlos", "Daniel", "Diego", "Enrique", "Fernando",
        "Gonzalo", "Hugo", "Ignacio", "Javier", "Jorge", "Jose", "Juan",
        "Luis", "Manuel", "Marcos", "Mario", "Miguel", "Pablo", "Pedro",
        "Rafael", "Raul", "Ruben", "Santiago", "Sergio", "Victor",
    ],
}

LAST_NAMES: dict[str, list[str]] = {
    Rider.Nationality.SPAIN: [
        "Alonso", "Alvarez", "Blanco", "Castro", "Diaz", "Dominguez",
        "Fernandez", "Garcia", "Gimenez", "Gomez", "Gonzalez", "Hernandez",
        "Jimenez", "Lopez", "Martin", "Martinez", "Moreno", "Munoz",
        "Navarro", "Ortiz", "Perez", "Ramirez", "Rodriguez", "Ruiz",
        "Sanchez", "Torres",
    ],
}

_MIN_ATTRIBUTE = 1
_MAX_ATTRIBUTE = 100
_ATTRIBUTE_SPREAD = 12  # +/- roll applied to each weighted attribute
_AGE_RANGE = (18, 36)
_PEAK_AGE_RANGE = (24, 32)
_BUILD_SPREAD_CM = 6
_BUILD_SPREAD_KG = 5


def _clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def _roll_quality(rng: random.Random) -> int:
    weights = [w for w, _, _ in QUALITY_SPREAD]
    low, high = rng.choices(QUALITY_SPREAD, weights=weights, k=1)[0][1:]
    return rng.randint(low, high)


def _roll_attributes(
    speciality: str, quality: int, rng: random.Random
) -> dict[str, int]:
    profile = SPECIALITY_PROFILES[speciality]
    attributes = {}
    for name in ENGINE_ATTRIBUTES:
        base = quality * profile[name]
        rolled = base + rng.uniform(-_ATTRIBUTE_SPREAD, _ATTRIBUTE_SPREAD)
        attributes[name] = _clamp(round(rolled), _MIN_ATTRIBUTE, _MAX_ATTRIBUTE)
    return attributes


def _roll_build(speciality: str, rng: random.Random) -> tuple[int, int]:
    mean_height, mean_weight = BUILD_PROFILES[speciality]
    height = mean_height + rng.randint(-_BUILD_SPREAD_CM, _BUILD_SPREAD_CM)
    weight = mean_weight + rng.randint(-_BUILD_SPREAD_KG, _BUILD_SPREAD_KG)
    return height, weight


def _roll_potential(
    quality: int, best_attribute: int, age: int, peak_age: int, rng: random.Random
) -> int:
    """Potential consistent with age: a young rider's potential sits at or
    above their current best attribute (they have room to grow, and cannot
    already have exceeded their own ceiling); an old rider's may sit below
    it (they have already declined past it). See the plan's Design
    decisions, item 7's clamping rule.

    Driven off `best_attribute`, not `quality` — a speciality's profile
    weight (e.g. a Climber's 1.45 on climb) can roll an attribute well past
    `quality` itself, so quality alone is not a safe floor."""
    headroom = max(0, peak_age - age) * rng.uniform(1.5, 3.0)
    shortfall = max(0, age - peak_age) * rng.uniform(1.0, 2.5)
    potential = quality + headroom - shortfall
    if age <= peak_age:
        potential = max(potential, best_attribute)
    return _clamp(round(potential), _MIN_ATTRIBUTE, _MAX_ATTRIBUTE)


def _roll_name(nationality: str, rng: random.Random) -> str:
    first = rng.choice(FIRST_NAMES[nationality])
    last = rng.choice(LAST_NAMES[nationality])
    return f"{first} {last}"


def _roll_training_affinity(speciality: str, rng: random.Random) -> dict[str, float]:
    """A rider improves fastest in the attributes their speciality favours —
    spec item 9. Reuses SPECIALITY_PROFILES as the bias, plus per-rider
    noise so two riders of the same speciality are not identical here
    either."""
    profile = SPECIALITY_PROFILES[speciality]
    return {
        name: round(weight * rng.uniform(0.85, 1.15), 2)
        for name, weight in profile.items()
    }


def generate_rider(
    *,
    speciality: str | None = None,
    nationality: str | None = None,
    quality: int | None = None,
    age: int | None = None,
    rng: random.Random | None = None,
) -> Rider:
    """Build an unsaved, internally consistent Rider.

    `quality` is 1-100 and sets the overall level the five attributes are
    drawn around. All arguments are optional; anything omitted is rolled.
    Returns unsaved so callers can bulk_create.
    """
    rng = rng or random.Random()

    speciality = speciality or rng.choice(list(Rider.Speciality.values))
    nationality = nationality or rng.choice(list(Rider.Nationality.values))
    quality = quality if quality is not None else _roll_quality(rng)
    age = age if age is not None else rng.randint(*_AGE_RANGE)
    peak_age = rng.randint(*_PEAK_AGE_RANGE)

    attributes = _roll_attributes(speciality, quality, rng)
    height_cm, weight_kg = _roll_build(speciality, rng)
    potential = _roll_potential(quality, max(attributes.values()), age, peak_age, rng)

    return Rider(
        name=_roll_name(nationality, rng),
        nationality=nationality,
        speciality=speciality,
        age=age,
        height_cm=height_cm,
        weight_kg=weight_kg,
        potential=potential,
        peak_age=peak_age,
        decline_rate=rng.randint(_MIN_ATTRIBUTE, _MAX_ATTRIBUTE),
        injury_proneness=rng.randint(_MIN_ATTRIBUTE, _MAX_ATTRIBUTE),
        training_affinity=_roll_training_affinity(speciality, rng),
        **attributes,
    )


def generate_roster(
    size: int,
    *,
    team=None,
    rng: random.Random | None = None,
) -> list[Rider]:
    """A squad-sized group with a deliberate spread of quality.

    Draws quality from QUALITY_SPREAD so the group contains riders worth
    building around and riders worth selling — spec item 11, and the
    property #46 depends on.
    """
    rng = rng or random.Random()
    riders = [generate_rider(rng=rng) for _ in range(size)]
    if team is not None:
        for rider in riders:
            rider.team = team
    return riders
