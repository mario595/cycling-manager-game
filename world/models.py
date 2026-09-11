from __future__ import annotations

from django.db import models
from django.utils import timezone


class GameClock(models.Model):
    """The world's current game datetime. There is exactly one row, `pk=1`.

    A row rather than a settings value or a cache key, because an advance
    must take a database lock on the clock in the same transaction as the
    work it claims — see `world/README.md`, *Exactly-once*.

    Not a `TimeStampedModel`: `created_at`/`updated_at` would be a third kind
    of timestamp on a row that already carries game time (`current`) and real
    time (`last_advanced_at`), which is exactly the confusion this feature
    exists to remove.
    """

    current = models.DateTimeField(
        help_text="The world's current game datetime, aware UTC.",
    )
    last_advanced_at = models.DateTimeField(
        help_text="Real wall-clock time of the last successful advance.",
    )
    catch_up_hours = models.PositiveSmallIntegerField(
        default=72,
        help_text="Per-advance cap on how much game time one advance will work through.",
    )

    @classmethod
    def load(cls) -> GameClock:
        """The one clock row, created at the current real time on first call."""
        now = timezone.now()
        obj, _ = cls.objects.get_or_create(
            pk=1, defaults={"current": now, "last_advanced_at": now},
        )
        return obj

    def __str__(self) -> str:
        return f"clock at {self.current}"


class TickRun(models.Model):
    """A record of one advance of the world.

    Spec item 10: "did the world tick?" must be an answerable question.
    """

    class Trigger(models.TextChoices):
        CRON = "cron", "Cron"
        TO_NEXT = "to_next", "To next"
        DAY = "day", "Day"

    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Real time. Null means the run did not complete.",
    )
    from_game_time = models.DateTimeField(help_text="Clock before this run.")
    to_game_time = models.DateTimeField(
        help_text="Clock after this run. Equal to from_game_time when nothing moved.",
    )
    races_started = models.PositiveIntegerField(default=0)
    races_finished = models.PositiveIntegerField(default=0)
    capped = models.BooleanField(
        default=False,
        help_text="True when the catch-up cap limited this advance.",
    )
    trigger = models.CharField(
        max_length=20, choices=Trigger.choices, default=Trigger.CRON,
    )
    error = models.TextField(
        blank=True, default="",
        help_text="Traceback if the run failed. Empty on success.",
    )

    class Meta:
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["-started_at"])]

    def __str__(self) -> str:
        return f"tick at {self.started_at} ({self.trigger})"
