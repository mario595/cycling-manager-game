from __future__ import annotations

from django.db.models import Sum, QuerySet
from django.utils import timezone

from .models import STARTING_BALANCE, LedgerEntry


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