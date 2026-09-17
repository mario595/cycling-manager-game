from __future__ import annotations

from django.db import IntegrityError, transaction
from django.db.models import Count, Sum, QuerySet
from django.utils import timezone
from teams.models import Team

from .models import STARTING_BALANCE, WEEKLY_WAGE_PER_RIDER, LedgerEntry


def balance_for(team) -> int:
    """A team's balance: the sum of its ledger entries. The balance is
    derived, never stored — see economy/README.md, *The ledger is
    append-only*."""
    return (
        LedgerEntry.objects.filter(team=team).aggregate(total=Sum("amount"))["total"] or 0
    )


def entries_for(team) -> QuerySet[LedgerEntry]:
    """A team's ledger entries, newest first (the model default)."""
    return LedgerEntry.objects.filter(team=team)


def ensure_opening_balance(team) -> LedgerEntry:
    """Give `team` its starting balance, once.

    Idempotent (`get_or_create` on `kind=STARTING_BALANCE`), so a second
    call — re-running `seed_teams`, a reclaimed team — never double-credits
    a team.
    """
    entry, _ = LedgerEntry.objects.get_or_create(
        team=team,
        kind=LedgerEntry.Kind.STARTING_BALANCE,
        defaults={
            "amount": STARTING_BALANCE,
            "occurred_at": timezone.now(),
            "description": "Starting balance",
        },
    )
    return entry


def reset_to_starting_balance(team) -> LedgerEntry | None:
    """Bring `team`'s balance back to STARTING_BALANCE with a `takeover`
    entry — the append-only ledger's own idiom for a correction (economy/
    README.md, *The ledger is append-only*). Returns None when the balance
    already is STARTING_BALANCE, so a team claimed at exactly the starting
    amount does not get a meaningless zero-credit row."""
    delta = STARTING_BALANCE - balance_for(team)
    if delta == 0:
        return None
    return LedgerEntry.objects.create(
        team=team,
        kind=LedgerEntry.Kind.TAKEOVER,
        amount=delta,
        occurred_at=timezone.now(),
        description="Team taken over",
    )


def charge_weekly_wages(week) -> int:
    """Debit every team one combined wage entry for `week`. Returns how
    many entries were written.

    Called once per crossed week boundary from world.services.tick(),
    inside the loop over WeekTransition rows. Exactly-once comes from that
    WeekTransition row (unique on `week`, written before this runs); the
    (team, week) constraint below is a second line of defence.

    One atomic() per create, never one around the loop: an IntegrityError
    poisons the enclosing transaction in Django. Same shape as
    schedule.services.process_transitions and staff's
    _write_training_reports, for the same reason.
    """
    counts = dict(
        Team.objects.annotate(n=Count("riders")).values_list("pk", "n")
    )
    written = 0
    for team_id, rider_count in counts.items():
        with transaction.atomic():
            try:
                LedgerEntry.objects.create(
                    team_id=team_id,
                    kind=LedgerEntry.Kind.WAGES,
                    amount=-(rider_count * WEEKLY_WAGE_PER_RIDER),
                    occurred_at=week.starts_at,
                    week=week,
                    rider_count=rider_count,
                    description="Weekly wages",
                )
                written += 1
            except IntegrityError:
                continue          # already charged; correct outcome, not an error
    return written