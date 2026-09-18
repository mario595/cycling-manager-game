from __future__ import annotations

from django.db import IntegrityError, transaction
from django.db.models import Count, QuerySet, Sum
from teams.models import Team

from .models import (
    FANBASE_PER_POINT,
    MINIMUM_FANBASE,
    STARTING_BALANCE,
    STARTING_FANBASE,
    WEEKLY_FANBASE_DECAY,
    WEEKLY_WAGE_PER_RIDER,
    FanbaseEntry,
    LedgerEntry,
)


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


def fanbase_for(team) -> int:
    """A team's fanbase: the sum of its FanbaseEntry deltas. Derived,
    never stored — same discipline as balance_for."""
    return (
        FanbaseEntry.objects.filter(team=team).aggregate(total=Sum("delta"))["total"] or 0
    )


def fanbase_entries_for(team) -> QuerySet[FanbaseEntry]:
    """A team's fanbase history, newest first (the model default)."""
    return FanbaseEntry.objects.filter(team=team)


def ensure_starting_fanbase(team, *, at) -> FanbaseEntry:
    """Give `team` its starting fanbase, once.

    Idempotent (`get_or_create` on `kind=STARTING`), so a second call —
    re-running `seed_teams`, a reclaimed team — never double-credits a team.
    Mirror of `ensure_opening_balance`; `at` is game time, passed by the
    caller (economy/ may not import world/, AGENTS.md).
    """
    entry, _ = FanbaseEntry.objects.get_or_create(
        team=team,
        kind=FanbaseEntry.Kind.STARTING,
        defaults={
            "delta": STARTING_FANBASE,
            "occurred_at": at,
            "description": "Starting fanbase",
        },
    )
    return entry


def reset_fanbase(team, *, at) -> FanbaseEntry | None:
    """Bring `team`'s fanbase back to STARTING_FANBASE with a `takeover`
    row. Returns None when it already is STARTING_FANBASE.

    `at` is game time, the moment the takeover completes — the caller
    passes `world.services.now()` itself. See `reset_to_starting_balance`."""
    delta = STARTING_FANBASE - fanbase_for(team)
    if delta == 0:
        return None
    return FanbaseEntry.objects.create(
        team=team,
        kind=FanbaseEntry.Kind.TAKEOVER,
        delta=delta,
        occurred_at=at,
        description="Team taken over",
    )


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


def apply_weekly_fanbase(week, *, points_by_team: dict[int, int]) -> int:
    """Adjust every team's fanbase for `week`. Returns rows written.

    The week each team is scored against is the caller's job: this function
    takes the points as a plain dict — economy/ may not import competitions/
    (AGENTS.md). `world/services.py` passes the week that just completed,
    never the one opening (D2) — see economy/README.md, *Fanbase reads the
    completed week*.

    The delta is clamped so the resulting fanbase never falls below
    MINIMUM_FANBASE, and the *clamped* delta is what is stored (D4): the
    sum of rows is the fanbase, so clamping on read would make history and
    displayed value disagree. Called once per crossed week boundary from
    world.services.tick(); exactly-once comes from that WeekTransition row,
    the (team, week) constraint below being a second line of defence.
    """
    current = dict(
        FanbaseEntry.objects.values("team_id").annotate(total=Sum("delta"))
        .values_list("team_id", "total")
    )
    written = 0
    for team_id in Team.objects.values_list("pk", flat=True):
        points = points_by_team.get(team_id, 0)
        now_at = current.get(team_id) or 0
        raw = points * FANBASE_PER_POINT - WEEKLY_FANBASE_DECAY
        # Clamp the RESULT, store the delta that gets there (D4).
        delta = max(now_at + raw, MINIMUM_FANBASE) - now_at
        with transaction.atomic():
            try:
                FanbaseEntry.objects.create(
                    team_id=team_id,
                    kind=FanbaseEntry.Kind.WEEKLY,
                    delta=delta,
                    occurred_at=week.starts_at,
                    week=week,
                    points=points,
                    description="Weekly fanbase change",
                )
                written += 1
            except IntegrityError:
                continue          # already applied; correct outcome, not an error
    return written