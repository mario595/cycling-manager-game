"""Insolvency (#27): when a managed team can no longer pay its way, what it
owes to get back, and the weekly assessment that counts the strikes.

State is rows, not a flag: a `SolvencyCheck` is written only when it matters,
so the latest check in the current managerial spell *is* the state. See
`economy/README.md`, *Insolvency*.

`economy/` may not read `staff/` or `riders.development_squad` prices, so a
team's trainer salary and squad cost arrive as plain numbers from the caller —
the same inversion `charge_trainer_salaries` and
`charge_development_squad_costs` use.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


from django.db import IntegrityError, transaction

from schedule.models import Week
from teams.models import Team

from .models import MERCHANDISE_FANBASE_PER_CREDIT, SolvencyCheck
from .services import active_contract, balance_for, fanbase_for, payroll_for

#: Consecutive paydays with the target unmet before the team is lost, counting
#: the payday that opened the case (spec: "the fourth consecutive insolvent
#: payday"). Game balance, not deployment configuration.
INSOLVENCY_LOSS_STRIKES = 4

EMBARGO_MESSAGE = (
    "Your team is insolvent. Signing, bidding, hiring and squad upgrades are "
    "blocked until your balance is back to zero or above."
)


@dataclass(frozen=True)
class SolvencyOutcome:
    opened: list[int]       # team pks whose case opened at this payday
    lost: list[int]         # team pks whose strikes reached INSOLVENCY_LOSS_STRIKES
    written: int            # rows written


@dataclass(frozen=True)
class SolvencyStatus:
    insolvent: bool
    balance: int
    shortfall: int          # live, from the roster as it stands now
    target: int             # the shortfall at the last payday
    cut_so_far: int         # max(0, target - shortfall)
    outgoings: int
    income: int
    strikes: int
    paydays_left: int | None
    deadline: datetime | None


def regular_income(team, season) -> int:
    """Merchandise plus the signed sponsor's *base* payment. Prize money is
    left out — irregular, so counting it would swing the target with one race
    — and so is the sponsor's results-driven swing: the base is the promised
    figure. `season` may be None (off-season), which leaves merchandise only."""
    income = max(fanbase_for(team), 0) // MERCHANDISE_FANBASE_PER_CREDIT
    if season is not None:
        contract = active_contract(team, season)
        if contract is not None:
            income += contract.weekly_base
    return income


def regular_outgoings(team, *, trainer_salary: int, squad_cost: int) -> int:
    return payroll_for(team) + trainer_salary + squad_cost


def weekly_shortfall(team, season, *, trainer_salary: int, squad_cost: int) -> int:
    """Regular weekly outgoings minus regular weekly income, floored at 0."""
    outgoings = regular_outgoings(team, trainer_salary=trainer_salary, squad_cost=squad_cost)
    return max(0, outgoings - regular_income(team, season))


def _current_spell_checks(team):
    """The team's checks since its current manager claimed it, newest first.

    A claimed team's older checks fall out of scope with no write in
    `claim_team`, which is how a claim clears insolvency without `teams/`
    knowing about it. A team claimed before `managed_since` existed (null)
    counts every check."""
    checks = SolvencyCheck.objects.filter(team=team)
    if team.managed_since is not None:
        checks = checks.filter(occurred_at__gte=team.managed_since)
    return checks


def open_check(team) -> SolvencyCheck | None:
    """The latest check of the current spell if its balance is negative."""
    latest = _current_spell_checks(team).first()
    return latest if latest is not None and latest.balance < 0 else None


def is_embargoed(team) -> bool:
    return open_check(team) is not None


def solvency_status(team, season, *, trainer_salary: int, squad_cost: int) -> SolvencyStatus:
    outgoings = regular_outgoings(team, trainer_salary=trainer_salary, squad_cost=squad_cost)
    income = regular_income(team, season)
    shortfall = max(0, outgoings - income)
    check = open_check(team)
    if check is None:
        return SolvencyStatus(
            insolvent=False, balance=balance_for(team), shortfall=shortfall, target=0,
            cut_so_far=0, outgoings=outgoings, income=income, strikes=0,
            paydays_left=None, deadline=None,
        )

    paydays_left = None
    deadline = None
    if shortfall > 0:
        paydays_left = max(INSOLVENCY_LOSS_STRIKES - check.strikes, 0)
        upcoming = list(
            Week.objects.filter(starts_at__gt=check.occurred_at)
            .order_by("starts_at")
            .values_list("starts_at", flat=True)[:paydays_left]
        )
        if paydays_left and len(upcoming) >= paydays_left:
            deadline = upcoming[paydays_left - 1]
    return SolvencyStatus(
        insolvent=True, balance=balance_for(team), shortfall=shortfall,
        target=check.shortfall, cut_so_far=max(0, check.shortfall - shortfall),
        outgoings=outgoings, income=income, strikes=check.strikes,
        paydays_left=paydays_left, deadline=deadline,
    )


def assess_solvency(
    week, *, salary_by_team: dict[int, int], squad_cost_by_team: dict[int, int],
) -> SolvencyOutcome:
    """Assess every managed team's solvency at `week`'s payday.

    Called once per crossed week from `world.services.tick()` after the week's
    money has moved. A row is written only for a team that is negative now or
    whose case is still open (so the recovery row exists); the strike rules
    are the table in `specs/insolvency-ladder-plan.md`, decision 4.

    Exactly-once: the (team, week) constraint backs the `WeekTransition` row,
    and a team already assessed for `week` is skipped without being reported
    as opened or lost — which is what stops a re-run tick releasing a team
    twice. One atomic() per create, never one around the loop.
    """
    opened: list[int] = []
    lost: list[int] = []
    written = 0
    for team in Team.objects.filter(manager__isnull=False).order_by("pk"):
        # A catch-up tick can cross a boundary that predates a claim; the new
        # manager is not judged on a week they were not running the team.
        if team.managed_since is not None and team.managed_since > week.starts_at:
            continue
        balance = balance_for(team)
        # Read BEFORE the create below, or it would see the row just written.
        previous = open_check(team)
        if balance >= 0 and previous is None:
            continue
        shortfall = weekly_shortfall(
            team, week.season,
            trainer_salary=salary_by_team.get(team.pk, 0),
            squad_cost=squad_cost_by_team.get(team.pk, 0),
        )
        if balance >= 0 or shortfall == 0:
            strikes = 0
        else:
            strikes = (previous.strikes if previous is not None else 0) + 1
        with transaction.atomic():
            try:
                SolvencyCheck.objects.create(
                    team=team, week=week, occurred_at=week.starts_at,
                    balance=balance, shortfall=shortfall, strikes=strikes,
                )
            except IntegrityError:
                continue          # already assessed; correct outcome, not an error
        written += 1
        if balance < 0 and previous is None:
            opened.append(team.pk)
        if strikes >= INSOLVENCY_LOSS_STRIKES:
            lost.append(team.pk)
    return SolvencyOutcome(opened=opened, lost=lost, written=written)
