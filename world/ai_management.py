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

import traceback

from economy.models import SponsorOffer
from economy.services import (
    AlreadySponsored,
    OfferNotAvailable,
    active_contract,
    balance_for,
    charge_trainer_fee,
    ensure_offer_round,
    payroll_for,
    sign_offer,
)
from riders.generation import SPECIALITY_PROFILES
from riders.models import ENGINE_ATTRIBUTES, Rider
from staff.models import Trainer
from staff.pricing import hire_fee, weekly_salary
from staff.services import (
    SlotOccupied,
    TrainerNotAvailable,
    available_trainers,
    focus_for,
    hire_trainer,
    set_focus,
    trainer_for,
)
from teams.models import Team

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


def _unmanaged_teams():
    return Team.objects.filter(manager__isnull=True).order_by("pk")


def hire_ai_trainers(at) -> tuple[int, str]:
    """Every unmanaged team without a trainer hires the cheapest one left in
    the pool, if it can afford to. Team-pk order, one trainer each, so the
    outcome is deterministic and a short pool leaves the later teams to try
    again at the next week boundary.

    The fee is booked inside hire_trainer's charge callback, so a failed
    hire rolls the ledger row back with it. Returns (hires, error text).
    """
    hired = 0
    error = ""
    pool = list(available_trainers())

    for team in _unmanaged_teams():
        if trainer_for(team) is not None:
            continue
        trainer = cheapest_trainer(pool)
        if trainer is None:
            break
        if not can_afford_trainer(balance_for(team), payroll_for(team), trainer):
            continue

        def charge(picked, team=team):
            charge_trainer_fee(
                team, amount=-hire_fee(picked), at=at, description=f"Hired {picked.name}",
            )

        try:
            hire_trainer(team, trainer.pk, charge=charge)
        except TrainerNotAvailable:
            # A human hired them since the pool was read. A normal outcome,
            # not an error; the next team tries the next cheapest.
            pool.remove(trainer)
            continue
        except SlotOccupied:
            # The slot filled under us; the trainer is still in the pool.
            continue
        except Exception:
            error += f"ai trainer hire for team {team.pk}:\n{traceback.format_exc()}\n"
            continue
        pool.remove(trainer)
        hired += 1

    return hired, error


def set_ai_focuses(week) -> int:
    """Set this week's training focus for every unmanaged team that has a
    trainer, by the rotation in focus_for_week. Writes only where the focus
    changes, so a re-run for the same week is a no-op. Returns how many
    focuses changed.
    """
    changed = 0
    for team in _unmanaged_teams():
        if trainer_for(team) is None:
            continue
        focus = focus_for_week(list(team.riders.all()), week.number, team.pk)
        if focus is None or focus == focus_for(team):
            continue
        set_focus(team, focus)
        changed += 1
    return changed


def sign_ai_sponsors(season, at) -> tuple[int, str]:
    """Every unmanaged team without a contract for `season` signs that
    season's steady offer.

    ensure_offer_round runs first: it no-ops on a team that already has a
    round, and gives one back to a team whose round a claim cleared before
    its manager was released. Returns (contracts signed, error text).
    """
    signed = 0
    error = ""
    for team in _unmanaged_teams():
        if active_contract(team, season) is not None:
            continue
        try:
            ensure_offer_round(team, season, at=at)
            offer = SponsorOffer.objects.filter(
                team=team, season=season, profile=AI_SPONSOR_PROFILE,
            ).first()
            if offer is None:
                continue
            sign_offer(team, offer.pk, at=at)
        except (AlreadySponsored, OfferNotAvailable):
            # Signed or cleared under us since the check. Not an error.
            continue
        except Exception:
            error += f"ai sponsor signing for team {team.pk}:\n{traceback.format_exc()}\n"
            continue
        signed += 1
    return signed, error
