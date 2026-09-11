from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta

from django.db import transaction
from django.utils import timezone

from .models import GameClock


class Clock(ABC):
    """What game code is handed when it asks what time it is. `now()` is the
    only method, deliberately: a caller holding a Clock has no business
    moving it, only reading it. See world/README.md, *The clock discipline
    rule*."""

    @abstractmethod
    def now(self) -> datetime: ...


class RealClock(Clock):
    """Production's clock. No state, no database — the game's time is the
    literal current time, read live."""

    def now(self) -> datetime:
        return timezone.now()


class MockClock(Clock):
    """Development- and test-only clock, backed by the single `GameClock`
    row. `world.services.get_clock()` is the only sanctioned way to obtain
    the active clock; do not import this class to bypass `mock_clock`'s
    isinstance guard.
    """

    def now(self) -> datetime:
        return GameClock.load().current

    def set(self, when: datetime) -> None:
        with transaction.atomic():
            clock = GameClock.objects.select_for_update().get(pk=1)
            clock.current = when
            clock.save(update_fields=["current"])

    def advance_by(self, delta: timedelta) -> None:
        with transaction.atomic():
            clock = GameClock.objects.select_for_update().get(pk=1)
            clock.current += delta
            clock.save(update_fields=["current"])

    def advance_to_next_due(self) -> None:
        """Jump straight to the next scheduled race's starts_at, or do
        nothing if none is scheduled after the current moment."""
        from racing.models import Race

        with transaction.atomic():
            clock = GameClock.objects.select_for_update().get(pk=1)
            nxt = (
                Race.objects.filter(
                    status=Race.Status.SCHEDULED, starts_at__isnull=False,
                    starts_at__gt=clock.current,
                )
                .order_by("starts_at")
                .first()
            )
            if nxt is not None:
                clock.current = nxt.starts_at
                clock.save(update_fields=["current"])
