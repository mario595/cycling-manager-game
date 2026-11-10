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
from dataclasses import dataclass

from django.db import transaction
from teams.models import Team

from .development_squad import squad_for
from .generation import generate_rider
from .models import DevelopmentSquad, Rider
from .services import record_initial_snapshots
from .youth_triage import free_places

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


@dataclass(frozen=True)
class IntakeResult:
    """What one intake run did, across every open squad: how many riders
    arrived, and how many were turned away for want of a place.

    `turned_away` is the pair the squad screen warns with before the week
    arrives, so the count has to be reported rather than inferred.
    """

    created: int
    turned_away: int


def run_intake(*, at, rng: random.Random | None = None) -> IntakeResult:
    """Give every open development squad one batch of youth riders, dated
    `at` (the intake week's starts_at). world/ decides which weeks; this
    decides who.

    Every open squad gets a batch, managed or not (plan Design decision 9):
    a team released to the pool keeps its squad and keeps paying for it, so
    it keeps receiving riders too.

    **A batch fills the squad's free places and the remainder is lost.** Only
    `min(INTAKE_BATCH_SIZE, free_places(squad))` riders are even drawn: a
    fuller squad means fewer draws, which is equivalent for the odds and
    simpler than generating the batch and throwing some of it away. A squad
    with no room records nothing, which is why the (squad, intake_at)
    idempotency check below would let a re-run try again — the `WeekTransition`
    row remains the exactly-once guarantee (riders/README.md).
    """
    rng = rng or random.Random()
    created_total = 0
    turned_away_total = 0
    for team_id in list(DevelopmentSquad.objects.values_list("team_id", flat=True)):
        with transaction.atomic():
            # The same lock close_squad takes, so a close cannot delete the
            # squad between our read and our insert (plan Design decision 7).
            team = Team.objects.select_for_update().get(pk=team_id)
            squad = squad_for(team)  # re-read BY TEAM under the lock
            if squad is None:
                continue  # closed since we listed it
            if Rider.objects.filter(development_squad=squad, intake_at=at).exists():
                continue  # second line of defence: this batch already ran
            # Read under the lock, after the idempotency check, so a promotion
            # or a graduation cannot change the answer between the two.
            places = free_places(squad)
            batch_size = min(INTAKE_BATCH_SIZE, places)
            batch = [generate_youth_rider(squad.level, rng=rng) for _ in range(batch_size)]
            for rider in batch:
                rider.development_squad = squad
                rider.intake_at = at
            created = Rider.objects.bulk_create(batch)
            record_initial_snapshots(created)  # baseline for the attribute history
            created_total += len(created)
            turned_away_total += INTAKE_BATCH_SIZE - len(created)
    return IntakeResult(created=created_total, turned_away=turned_away_total)
