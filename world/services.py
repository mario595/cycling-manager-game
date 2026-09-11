"""The game clock: the one way any code asks what time it is, and the
machinery that finds and processes due work.

See `world/README.md` for the discipline this module enforces: game code
reads `now()`, never `timezone.now()` / `datetime.now()`, when deciding
whether something scheduled is due. `now()` reads whichever `Clock` is
configured (`settings.GAME_CLOCK_CLASS`) — real, live time in production,
a developer-controlled mock clock in dev/test.
"""

from __future__ import annotations

import traceback
from datetime import datetime

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.module_loading import import_string

from racing.models import Race
from racing.services import simulate_race
from schedule.models import SeasonTransition
from schedule.services import process_transitions

from .clocks import Clock
from .models import GameClock, TickRun

_clock: Clock | None = None


def get_clock() -> Clock:
    """The process-wide clock, resolved from `settings.GAME_CLOCK_CLASS` and
    cached. Exported (not underscore-prefixed) because `mock_clock`'s
    commands need it to call `MockClock`-only methods."""
    global _clock
    if _clock is None:
        _clock = import_string(settings.GAME_CLOCK_CLASS)()
    return _clock


def now() -> datetime:
    """The current game time. Every piece of game code asks here, never
    `timezone.now()` / `datetime.now()`."""
    return get_clock().now()


def _reclaim_unfinished() -> list[int]:
    """Race ids left `running` with no results by an interrupted run."""
    return list(
        Race.objects.filter(status=Race.Status.RUNNING, results__isnull=True)
        .order_by("starts_at")
        .values_list("pk", flat=True)
    )


def _claim(limit: int, at: datetime) -> list[int]:
    """Claim up to `limit` due races by flipping them SCHEDULED -> RUNNING
    inside a transaction holding a row lock on exactly those rows. Returns
    the claimed ids. No simulation happens here.

    A second `tick` arriving while this transaction holds the lock blocks on
    `select_for_update()`, then re-runs its own filter after this one
    commits — the rows just claimed are now RUNNING and no longer match, so
    the second claim gets nothing. This is the exactly-once guarantee; see
    world/README.md.
    """
    if limit <= 0:
        return []
    with transaction.atomic():
        ids = list(
            Race.objects.select_for_update()
            .filter(status=Race.Status.SCHEDULED, starts_at__isnull=False, starts_at__lte=at)
            .order_by("starts_at")
            .values_list("pk", flat=True)[:limit]
        )
        Race.objects.filter(pk__in=ids).update(status=Race.Status.RUNNING)
    return ids


def _execute(race_ids: list[int], tick: TickRun, at: datetime) -> None:
    """Simulate each claimed race outside any lock. One broken course must
    not stop the run: an exception is recorded on that race and on the
    tick, and the loop continues."""
    for race_id in race_ids:
        race = Race.objects.get(pk=race_id)
        try:
            simulate_race(race, game_time=at)
            tick.races_finished += 1
        except Exception:
            race.status = Race.Status.FAILED
            race.save(update_fields=["status"])
            tick.error += f"race {race_id}:\n{traceback.format_exc()}\n"


def tick() -> TickRun:
    """Find and process whatever is due, exactly once. The only entry point
    cron — or a developer, after moving the mock clock with `mock_clock` —
    ever calls."""
    max_races = GameClock.load().catch_up_max_races
    at = now()

    # Transitions before race claiming: a race in week 1 of a season that
    # has just opened should be processed in a world that has already
    # recorded the opening.
    transitions = process_transitions(at)

    reclaimed = _reclaim_unfinished()
    claimed = _claim(limit=max(0, max_races - len(reclaimed)), at=at)
    capped = len(reclaimed) + len(claimed) >= max_races

    run = TickRun.objects.create(
        races_started=len(claimed),
        seasons_opened=sum(1 for t in transitions if t.kind == SeasonTransition.Kind.OPENED),
        seasons_closed=sum(1 for t in transitions if t.kind == SeasonTransition.Kind.CLOSED),
    )
    _execute(reclaimed + claimed, run, at=at)
    run.capped = capped
    # Real time regardless of which clock is active: this records when the
    # check itself ran on the host, not game time. The one other sanctioned
    # real-time read alongside RealClock.now() itself.
    run.finished_at = timezone.now()
    run.save(update_fields=["races_finished", "capped", "error", "finished_at"])
    return run
