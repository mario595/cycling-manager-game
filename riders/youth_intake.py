"""Youth intake (#33): periodically populating an open development squad
with young riders of widely varying quality.

`world/` decides *when* intake runs — the cadence in game weeks, resolved
against the season calendar it owns. This module decides *what* a batch
looks like: how many riders, how old, and how their hidden potential is
drawn. `riders/` may not import `schedule/`, `economy/` or `world/`
(AGENTS.md), so this module receives a plain week number and a datetime,
never a `Week` — the same boundary `record_week_snapshots(week_id=...)`
keeps.
"""

from __future__ import annotations

import random

from .generation import generate_rider

INTAKE_INTERVAL_WEEKS = 4
INTAKE_BATCH_SIZE = 2
INTAKE_AGE_RANGE = (17, 19)

#: A youth's current ability is a fraction of their rolled potential —
#: "far below professional level" (the spec's *Player experience*), never
#: close to it. Clamped to at least 1 in generate_youth_rider.
YOUTH_QUALITY_FRACTION = (0.25, 0.40)

#: (low, high) potential per band, lowest band first. See the plan's
#: Design decision 10. A typical starting-roster rider has quality 21-35
#: and potential around 40-50 (generation.QUALITY_SPREAD); "promising"
#: ends above that, and "gem" ends well above.
POTENTIAL_BANDS: tuple[tuple[int, int], ...] = (
    (20, 35),   # hopeless
    (36, 50),   # journeyman
    (51, 65),   # promising
    (66, 85),   # gem
)

#: Band weights per DevelopmentSquad level, same order as POTENTIAL_BANDS.
#: Each column sums to 100. Three properties are enforced by tests, not
#: just these numbers: the share of promising-or-better rises strictly
#: with level, the bottom two bands are a majority at every level, and
#: every band has a non-zero weight at every level.
BAND_WEIGHTS: dict[int, tuple[int, ...]] = {
    1: (50, 35, 13, 2),
    2: (40, 37, 19, 4),
    3: (30, 37, 25, 8),
}


def is_intake_week(week_number: int) -> bool:
    """Whether `week_number` (1-12 within a season) is an intake week —
    every INTAKE_INTERVAL_WEEKS weeks, giving weeks 4, 8 and 12."""
    return week_number % INTAKE_INTERVAL_WEEKS == 0


def generate_youth_rider(level: int, *, rng: random.Random):
    """One unsaved youth Rider for a squad running at `level`.

    Potential is rolled first, from a band whose odds are set by `level`
    (BAND_WEIGHTS), then current ability is derived from it — the reverse
    of ordinary generation, so the level has a direct handle on the trait
    that actually decides whether a youth is worth developing (plan Design
    decision 10)."""
    weights = BAND_WEIGHTS[level]
    low, high = rng.choices(POTENTIAL_BANDS, weights=weights, k=1)[0]
    potential = rng.randint(low, high)
    quality = max(1, round(potential * rng.uniform(*YOUTH_QUALITY_FRACTION)))
    age = rng.randint(*INTAKE_AGE_RANGE)
    return generate_rider(quality=quality, age=age, potential=potential, rng=rng)
