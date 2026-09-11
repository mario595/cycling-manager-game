"""The game clock: the one way any code asks what time it is, and the
machinery that advances it.

See `world/README.md` for the discipline this module enforces: game code
reads `now()`, never `timezone.now()` / `datetime.now()`, when deciding
whether something scheduled is due. The one sanctioned exception is
`_claim`'s read of `timezone.now()`, used only to compute how far real time
has moved since the last advance.
"""

from __future__ import annotations

import traceback
from datetime import datetime, timedelta

from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from racing.models import Race
from racing.services import simulate_race

from .models import GameClock, TickRun


def now() -> datetime:
    """The current game time. Every piece of game code asks here, never
    `timezone.now()` / `datetime.now()`."""
    return GameClock.load().current


def due_races(before: datetime) -> QuerySet[Race]:
    """Scheduled races whose start time is at or before `before`."""
    return Race.objects.filter(
        status=Race.Status.SCHEDULED, starts_at__isnull=False, starts_at__lte=before,
    ).order_by("starts_at")


def _reclaim_unfinished() -> list[int]:
    """Race ids left `running` with no results by an interrupted run."""
    return list(
        Race.objects.filter(status=Race.Status.RUNNING, results__isnull=True)
        .order_by("starts_at")
        .values_list("pk", flat=True)
    )


def _claim(clock_pk: int, to_next: bool, days: int) -> tuple[datetime, datetime, list[int], bool]:
    """Move the clock and claim what is due. Returns (before, after, race_ids, capped).

    Everything here runs inside one transaction holding a row lock on the
    clock. It does NO simulation: races are only flipped to RUNNING, and the
    work happens after this returns and the lock is released.
    """
    with transaction.atomic():
        clock = GameClock.objects.select_for_update().get(pk=clock_pk)
        before = clock.current
        cap = timedelta(hours=clock.catch_up_hours)

        if days:
            horizon, capped = before + timedelta(days=days), False
        elif to_next:
            nxt = (
                Race.objects.filter(
                    status=Race.Status.SCHEDULED, starts_at__isnull=False, starts_at__gt=before,
                )
                .order_by("starts_at")
                .first()
            )
            horizon = nxt.starts_at if nxt else before
            capped = False
        else:
            # Production: never move further than real time has, nor than the cap.
            # `timezone.now()` here is the ONE sanctioned read of real time.
            elapsed = timezone.now() - clock.last_advanced_at
            horizon = before + min(elapsed, cap)
            capped = elapsed > cap

        race_ids = list(
            Race.objects.filter(
                status=Race.Status.SCHEDULED,
                starts_at__isnull=False,
                starts_at__gt=before,
                starts_at__lte=horizon,
            ).order_by("starts_at").values_list("pk", flat=True)
        )
        Race.objects.filter(pk__in=race_ids).update(status=Race.Status.RUNNING)

        clock.current = horizon
        clock.last_advanced_at = timezone.now()
        clock.save(update_fields=["current", "last_advanced_at"])

    return before, horizon, race_ids, capped


def _execute(race_ids: list[int], game_time: datetime, tick: TickRun) -> None:
    """Simulate each claimed race outside any clock transaction. One broken
    course must not stop the world: an exception is recorded on that race
    and on the tick, and the loop continues."""
    for race_id in race_ids:
        race = Race.objects.get(pk=race_id)
        try:
            simulate_race(race, game_time=game_time)
            tick.races_finished += 1
        except Exception:
            race.status = Race.Status.FAILED
            race.save(update_fields=["status"])
            tick.error += f"race {race_id}:\n{traceback.format_exc()}\n"


def advance(trigger: str = TickRun.Trigger.CRON, to_next: bool = False, days: int = 0) -> TickRun:
    """Advance the world once and return the record of what happened."""
    clock = GameClock.load()

    reclaimed = _reclaim_unfinished()

    if days:
        before, horizon, race_ids = _advance_days(clock.pk, days)
        capped = False
    else:
        before, horizon, race_ids, capped = _claim(clock.pk, to_next, days=0)

    tick = TickRun.objects.create(
        from_game_time=before, to_game_time=horizon,
        races_started=len(race_ids), trigger=trigger,
    )
    _execute(reclaimed + race_ids, horizon, tick)
    tick.capped = capped
    tick.finished_at = timezone.now()
    tick.save(update_fields=["races_finished", "capped", "error", "finished_at"])
    return tick


def _advance_days(clock_pk: int, days: int) -> tuple[datetime, datetime, list[int]]:
    """Process everything within `days` game days by repeatedly jumping to
    the next scheduled moment, until the clock passes the target. Written as
    a loop over `_claim` rather than reimplementing the claim logic a second
    time (spec item 8, plan decision on `--day`).
    """
    origin = GameClock.objects.get(pk=clock_pk).current
    target = origin + timedelta(days=days)
    all_race_ids: list[int] = []
    horizon = origin

    while True:
        before, next_horizon, race_ids, _ = _claim(clock_pk, to_next=True, days=0)
        if next_horizon == before:
            # Nothing left scheduled: the claim did not move the clock.
            break
        all_race_ids += race_ids
        horizon = next_horizon
        if horizon >= target:
            break

    if horizon < target:
        with transaction.atomic():
            clock = GameClock.objects.select_for_update().get(pk=clock_pk)
            clock.current = target
            clock.last_advanced_at = timezone.now()
            clock.save(update_fields=["current", "last_advanced_at"])
        horizon = target

    return origin, horizon, all_race_ids
