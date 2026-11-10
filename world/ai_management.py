"""How unmanaged teams run their staff and sponsorship.

Pure helpers first (a roster in, a decision out), then orchestrators the tick
calls. Same shape as ai_market.py and for the same reason: world/ is the only
place staff/ and economy/ can meet. See `specs/unmanaged-team-heuristic-ai.md`
and `specs/unmanaged-team-heuristic-ai-plan.md` for the reasoning behind each
rule.

Like the market, nothing here reads a hidden rider trait: the focus comes from
a rider's speciality and the hire from a trainer's price, both visible.
"""

from __future__ import annotations

from riders.generation import SPECIALITY_PROFILES
from riders.models import ENGINE_ATTRIBUTES, Rider
from staff.models import Trainer
from staff.pricing import hire_fee, weekly_salary

#: A season of outgoings — wages plus the new trainer's salary — must still
#: be covered after the hire fee is paid. A runway check, deliberately not
#: the market's AI_CUSHION_FRACTION, which is a spending fraction.
AI_STAFF_RESERVE_WEEKS = 12
#: Unmanaged teams always sign the low-variance offer.
AI_SPONSOR_PROFILE = "steady"


def dominant_attribute(speciality: str) -> str:
    """The attribute a speciality's generation profile weights highest.

    Ties go to the earlier attribute in ENGINE_ATTRIBUTES, so the answer
    never depends on dict order.
    """
    profile = SPECIALITY_PROFILES[speciality]
    return max(ENGINE_ATTRIBUTES, key=lambda name: (profile[name], -ENGINE_ATTRIBUTES.index(name)))


def focus_for_week(riders: list[Rider], week_number: int, team_pk: int) -> str | None:
    """This week's training focus for a roster, or None for an empty one.

    One entry per rider, in pk order, walked by week number: a climber-heavy
    team trains climb most weeks, and every speciality on the roster gets
    turns. Offset by team pk so unmanaged teams do not all train the same
    thing in the same week. Deterministic, never random, so a re-run tick
    makes the same choice.
    """
    if not riders:
        return None
    attributes = [dominant_attribute(r.speciality) for r in sorted(riders, key=lambda r: r.pk)]
    return attributes[(week_number + team_pk) % len(attributes)]


def cheapest_trainer(pool: list[Trainer]) -> Trainer | None:
    """The pool trainer with the lowest hire fee, ties to the lower pk.

    Never the best: the AI leaves quality to the humans.
    """
    if not pool:
        return None
    return min(pool, key=lambda t: (hire_fee(t), t.pk))


def can_afford_trainer(balance: int, payroll: int, trainer: Trainer) -> bool:
    """Would `balance`, after the hire fee, still cover AI_STAFF_RESERVE_WEEKS
    of wages plus this trainer's salary?"""
    reserve = AI_STAFF_RESERVE_WEEKS * (payroll + weekly_salary(trainer))
    return balance - hire_fee(trainer) >= reserve
