from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timedelta

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
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

    A stopped clock: it shows `GameClock.current` until someone moves it.
    Every write also stamps `GameClock.anchored_at` (real time), which this
    class ignores and `AcceleratedClock` builds on — so switching between the
    two in settings never meets a stale anchor. See world/README.md, *The
    accelerated clock (#129)*.
    """

    def now(self) -> datetime:
        return self._effective(GameClock.load(), timezone.now())

    def _effective(self, row: GameClock, real_now: datetime) -> datetime:
        """The game time `row` shows at real time `real_now`. Stopped here."""
        return row.current

    def _locked(self) -> GameClock:
        GameClock.load()  # make sure the row exists before locking it
        return GameClock.objects.select_for_update().get(pk=1)

    @staticmethod
    def _write(row: GameClock, game_time: datetime, real_now: datetime, **fields) -> None:
        """Re-anchor: `game_time` is what the clock shows at `real_now`."""
        row.current = game_time
        row.anchored_at = real_now
        for name, value in fields.items():
            setattr(row, name, value)
        row.save(update_fields=["current", "anchored_at", *fields])

    def set(self, when: datetime) -> None:
        with transaction.atomic():
            row = self._locked()
            self._write(row, when, timezone.now())

    def advance_by(self, delta: timedelta) -> None:
        # Load-bearing: add the delta to the *effective* time, never to
        # row.current — under AcceleratedClock that would drop every game
        # minute that has flowed since the last anchor.
        with transaction.atomic():
            row = self._locked()
            real_now = timezone.now()
            self._write(row, self._effective(row, real_now) + delta, real_now)

    def advance_to_next_due(self) -> None:
        """Jump straight to the next scheduled race's starts_at, or do
        nothing if none is scheduled after the current moment."""
        from racing.models import Race

        with transaction.atomic():
            row = self._locked()
            real_now = timezone.now()
            current = self._effective(row, real_now)
            nxt = (
                Race.objects.filter(
                    status=Race.Status.SCHEDULED, starts_at__isnull=False,
                    starts_at__gt=current,
                )
                .order_by("starts_at")
                .first()
            )
            if nxt is not None:
                self._write(row, nxt.starts_at, real_now)


class AcceleratedClock(MockClock):
    """The staging world's clock (#129): game time flows at
    `settings.GAME_CLOCK_SPEED` times real time, continuously, so every read
    sees a later time than the one before — the way production's clock
    behaves, only faster.

    The row is an anchor: `current` is the game time at the real moment
    `anchored_at`. Freezing stores the flag on the row (gunicorn workers and
    the cron tick are separate processes) and stops time at the moment of
    freezing; resuming re-anchors there, so no game time is skipped. Being a
    MockClock, it can still be set and moved by `mock_clock`.
    """

    @property
    def speed(self) -> int:
        speed = getattr(settings, "GAME_CLOCK_SPEED", 1)
        if not isinstance(speed, int) or speed < 1:
            raise ImproperlyConfigured(
                f"GAME_CLOCK_SPEED must be a whole number of at least 1, got {speed!r}"
            )
        return speed

    @property
    def frozen(self) -> bool:
        return GameClock.load().frozen

    def _effective(self, row: GameClock, real_now: datetime) -> datetime:
        if row.frozen or row.anchored_at is None:
            return row.current
        return row.current + (real_now - row.anchored_at) * self.speed

    def freeze(self) -> bool:
        """Stop game time where it is. Returns False if already frozen."""
        with transaction.atomic():
            row = self._locked()
            if row.frozen:
                return False
            real_now = timezone.now()
            self._write(row, self._effective(row, real_now), real_now, frozen=True)
            return True

    def resume(self) -> bool:
        """Let game time flow again from the frozen moment. Returns False if
        it was not frozen."""
        with transaction.atomic():
            row = self._locked()
            if not row.frozen:
                return False
            self._write(row, row.current, timezone.now(), frozen=False)
            return True
