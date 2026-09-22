from __future__ import annotations

from django.db import models
from django.utils import timezone


class GameClock(models.Model):
    """The mock clock's current value. There is exactly one row, `pk=1`.

    **Only meaningful when `world.clocks.MockClock` is the configured
    clock** (`settings.GAME_CLOCK_CLASS`, dev/test default). In production,
    with `RealClock` active, this row is never read or written — `now()`
    returns live real time directly instead. See `world/README.md`, *Which
    clock runs where*.

    A row rather than a settings value or a cache key, because moving it
    must take a database lock in the same transaction as any read racing
    against it — see `world/README.md`, *Exactly-once*.
    """

    current = models.DateTimeField(
        help_text="The mock clock's value, aware UTC. Unused when RealClock is active.",
    )
    catch_up_max_races = models.PositiveSmallIntegerField(
        default=50,
        help_text="Per-tick cap on how many due races one tick will claim. Applies regardless of which clock is active.",
    )

    @classmethod
    def load(cls) -> GameClock:
        """The one clock row, created at the current real time on first call."""
        now = timezone.now()
        obj, _ = cls.objects.get_or_create(pk=1, defaults={"current": now})
        return obj

    def __str__(self) -> str:
        return f"clock at {self.current}"


class TickRun(models.Model):
    """A record of one tick: what it found due and what it did.

    Spec item 8: "did anything run, and did it work?" must be an answerable
    question.
    """

    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Real time. Null means the run did not complete.",
    )
    races_started = models.PositiveIntegerField(default=0)
    races_finished = models.PositiveIntegerField(default=0)
    capped = models.BooleanField(
        default=False,
        help_text="True when catch_up_max_races limited this run.",
    )
    seasons_opened = models.PositiveSmallIntegerField(default=0)
    seasons_closed = models.PositiveSmallIntegerField(default=0)
    weeks_processed = models.PositiveSmallIntegerField(
        default=0,
        help_text="How many week boundaries this tick recorded (#58).",
    )
    riders_aged = models.PositiveIntegerField(
        default=0,
        help_text="How many riders had their age advanced this tick (#58).",
    )
    riders_trained = models.PositiveIntegerField(
        default=0,
        help_text="How many riders had a *displayed* attribute change from training "
        "and/or racing this tick (#36).",
    )
    wage_entries = models.PositiveIntegerField(
        default=0,
        help_text="Ledger wage entries written this tick.",
    )
    merchandise_entries = models.PositiveIntegerField(
        default=0,
        help_text="Ledger merchandise entries written this tick (#21).",
    )
    trainer_salary_entries = models.PositiveIntegerField(
        default=0,
        help_text="Ledger trainer salary entries written this tick (#69).",
    )
    fanbase_entries = models.PositiveIntegerField(
        default=0,
        help_text="Fanbase change entries written this tick (#21).",
    )
    sponsorship_entries = models.PositiveIntegerField(
        default=0,
        help_text="Sponsorship ledger entries written this tick (#22).",
    )
    error = models.TextField(
        blank=True, default="",
        help_text="Traceback if the run failed. Empty on success.",
    )

    class Meta:
        ordering = ["-started_at"]
        indexes = [models.Index(fields=["-started_at"])]

    def __str__(self) -> str:
        return f"tick at {self.started_at}"
