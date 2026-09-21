from __future__ import annotations

from django.db import IntegrityError, transaction
from django.db.models import Count, QuerySet, Sum
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


def ensure_opening_balance(team, *, at) -> LedgerEntry:
    """Give `team` its starting balance, once.

    Idempotent (`get_or_create` on `kind=STARTING_BALANCE`), so a second
    call — re-running `seed_teams`, a reclaimed team — never double-credits
    a team.

    `at` is game time, the moment the balance is granted — the caller
    (world/, api/, or `teams/`'s seed command) passes `world.services.now()`
    itself. economy/ may not import world/ (AGENTS.md).
    """
    entry, _ = LedgerEntry.objects.get_or_create(
        team=team,
        kind=LedgerEntry.Kind.STARTING_BALANCE,
        defaults={
            "amount": STARTING_BALANCE,
            "occurred_at": at,
            "description": "Starting balance",
        },
    )
    return entry


def reset_to_starting_balance(team, *, at) -> LedgerEntry | None:
    """Bring `team`'s balance back to STARTING_BALANCE with a `takeover`
    entry — the append-only ledger's own idiom for a correction (economy/
    README.md, *The ledger is append-only*). Returns None when the balance
    already is STARTING_BALANCE, so a team claimed at exactly the starting
    amount does not get a meaningless zero-credit row.

    `at` is game time, the moment the takeover completes — the caller
    passes `world.services.now()` itself. See `ensure_opening_balance`."""
    delta = STARTING_BALANCE - balance_for(team)
    if delta == 0:
        return None
    return LedgerEntry.objects.create(
        team=team,
        kind=LedgerEntry.Kind.TAKEOVER,
        amount=delta,
        occurred_at=at,
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


def pay_race_prizes(race_id: int, *, race_name: str, at,
                    prizes_by_team: dict[int, list[tuple[int, int]]]) -> int:
    """Credit every team its prize money for one race. Returns rows written.

    Takes the race as an id plus the amounts already computed by
    competitions.services.prizes_by_team — economy/ may not import
    racing/ or competitions/ (AGENTS.md), so it never reads a RaceResult
    itself. The identical shape apply_weekly_fanbase takes points_by_team.

    Idempotent through the (team, race, position) constraint, not an
    early return: a partial payout (interrupted mid-loop) must be
    completable on retry, unlike score_race's early return which only
    ever needs to check for the presence of one row per team.
    """
    written = 0
    description = f"Prize money — {race_name}"[:120]
    for team_id, placements in prizes_by_team.items():
        for position, amount in placements:
            with transaction.atomic():
                try:
                    LedgerEntry.objects.create(
                        team_id=team_id,
                        kind=LedgerEntry.Kind.PRIZE_MONEY,
                        amount=amount,
                        occurred_at=at,
                        race_id=race_id,
                        position=position,
                        description=description,
                    )
                    written += 1
                except IntegrityError:
                    continue      # already paid; correct outcome, not an error
    return written