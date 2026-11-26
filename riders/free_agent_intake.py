"""Free-agent intake (#157): new riders join the free-agent pool on a
regular cadence, so the pool is never empty for long.

Before this, the pool only ever filled when a rider left a team, and a
fresh world has nobody leaving. Retirement took about one rider a season
from every team and nothing came back. Unmanaged teams, which only sign
from the pool, shrank season after season until they could no longer sell
a rider at auction.

`world/` decides *when* an intake runs: it passes a week number and the
week's start. This module decides *who* arrives. Like youth intake, it never
sees a `Week`, since `riders/` may not import `schedule/`.

Nothing here removes riders. Free-agent expiry (`world.services.
_expire_free_agents`) already retires or deletes the weakest riders nobody
signed in `EXPIRY_WEEKS`, so intake and expiry together keep the pool
turning over instead of growing without limit.
"""

from __future__ import annotations

import random

from django.db import transaction

from .field_level import current_field_factor
from .generation import generate_rider
from .models import Rider
from .services import record_initial_snapshots

#: An intake every other week: six a season.
FREE_AGENT_INTAKE_INTERVAL_WEEKS = 2
#: Six riders an intake, 36 a season. That is about twice what retirement
#: takes from a 16-team world in a season (17 at the first close of a seeded
#: one), so unmanaged teams can fill their gaps and humans still have a choice.
FREE_AGENT_INTAKE_SIZE = 6
#: Old enough to race now and young enough to be years from the 33-38
#: retirement window. Quality is rolled like any generated rider's, so most
#: are ordinary and a few are worth fighting for.
FREE_AGENT_AGE_RANGE = (19, 28)


def is_free_agent_intake_week(week_number: int) -> bool:
    """Whether `week_number` (1-12 within a season) brings an intake:
    weeks 2, 4, ..., 12."""
    return week_number % FREE_AGENT_INTAKE_INTERVAL_WEEKS == 0


def generate_free_agent(*, rng: random.Random) -> Rider:
    """One unsaved intake rider: any speciality, rolled quality, aged
    within FREE_AGENT_AGE_RANGE."""
    return generate_rider(
        age=rng.randint(*FREE_AGENT_AGE_RANGE), rng=rng, field_factor=current_field_factor(),
    )


def run_free_agent_intake(*, at, rng: random.Random | None = None) -> list[Rider]:
    """Add FREE_AGENT_INTAKE_SIZE new riders to the free-agent pool, stamped
    `unattached_since = at` (the intake week's starts_at), so expiry counts
    their eight weeks from the day they arrived. Returns the created riders.

    Exactly-once comes from the caller: world/ runs this inside its week
    loop, which applies each WeekTransition once ever.
    """
    rng = rng or random.Random()
    batch = [generate_free_agent(rng=rng) for _ in range(FREE_AGENT_INTAKE_SIZE)]
    for rider in batch:
        rider.unattached_since = at
    with transaction.atomic():
        created = Rider.objects.bulk_create(batch)
        record_initial_snapshots(created)  # baseline for the attribute history
    return created
