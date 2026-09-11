from __future__ import annotations

from datetime import time, timedelta

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel

SEASON_WEEKS = 12


class Season(TimeStampedModel):
    """A numbered racing season, twelve weeks long.

    `starts_at`/`ends_at` are **game** time — the range the season occupies
    on the clock. `created_at`/`updated_at` (from `TimeStampedModel`) are
    real time: when this row was declared, never confused with when the
    season itself runs. See `schedule/README.md`, *Derived, not stored* —
    there is deliberately no "is this the current season" field anywhere;
    `schedule.services.current_position()` answers that from `starts_at`/
    `ends_at` alone.
    """

    number = models.PositiveIntegerField(unique=True, help_text="Starts at 1.")
    starts_at = models.DateTimeField(
        help_text="Game time. Must be a Monday at 00:00:00 UTC — see schedule/README.md.",
    )
    ends_at = models.DateTimeField(
        help_text="Game time. Derived: starts_at + twelve weeks, set automatically on save.",
    )

    class Meta:
        ordering = ["number"]
        indexes = [
            models.Index(fields=["starts_at", "ends_at"], name="season_range_idx"),
        ]

    def __str__(self) -> str:
        return f"Season {self.number}"

    def clean(self):
        super().clean()
        if self.starts_at is None:
            return
        starts_at_utc = timezone.localtime(self.starts_at, timezone.utc)
        if starts_at_utc.weekday() != 0 or starts_at_utc.time() != time(0, 0, 0):
            raise ValidationError({
                "starts_at": "must be a Monday at 00:00:00 UTC",
            })
        ends_at = self.starts_at + timedelta(weeks=SEASON_WEEKS)
        overlapping = Season.objects.filter(
            starts_at__lt=ends_at, ends_at__gt=self.starts_at,
        ).exclude(pk=self.pk)
        if overlapping.exists():
            raise ValidationError({
                "starts_at": "overlaps an existing season's range",
            })

    def save(self, *args, **kwargs):
        if self.ends_at is None and self.starts_at is not None:
            self.ends_at = self.starts_at + timedelta(weeks=SEASON_WEEKS)
        super().save(*args, **kwargs)


class Week(models.Model):
    """One of a season's twelve weeks — a real row, not a display-only
    derivation, so the race calendar (#7) has somewhere to place races into.

    Not a `TimeStampedModel`: a Week is created only alongside its season by
    `load_season` and never touched again, so real-time audit columns on
    twelve rows per season would be noise.
    """

    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="weeks")
    number = models.PositiveSmallIntegerField(help_text="1 to 12.")
    starts_at = models.DateTimeField(help_text="Game time.")
    ends_at = models.DateTimeField(help_text="Game time.")

    class Meta:
        ordering = ["season", "number"]
        constraints = [
            models.UniqueConstraint(fields=["season", "number"], name="unique_week_per_season"),
        ]
        indexes = [
            models.Index(fields=["starts_at", "ends_at"], name="week_range_idx"),
        ]

    def __str__(self) -> str:
        return f"Season {self.season.number}, Week {self.number}"


class SeasonTransition(TimeStampedModel):
    """The exactly-once record of a season opening or closing.

    Written only by `schedule.services.process_transitions()`, called from
    `world.services.tick()`. See `schedule/README.md`, *Exactly-once* — the
    `unique_transition_per_season` constraint is the guarantee, not an
    optimisation.
    """

    class Kind(models.TextChoices):
        OPENED = "opened", "Opened"
        CLOSED = "closed", "Closed"

    season = models.ForeignKey(Season, on_delete=models.CASCADE, related_name="transitions")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    occurred_at = models.DateTimeField(
        help_text="Game time the boundary was crossed — the season's own starts_at/ends_at, not the moment the tick noticed.",
    )
    recorded_at = models.DateTimeField(
        auto_now_add=True,
        help_text="Real time the tick wrote this row.",
    )

    class Meta:
        ordering = ["-occurred_at"]
        constraints = [
            models.UniqueConstraint(fields=["season", "kind"], name="unique_transition_per_season"),
        ]

    def __str__(self) -> str:
        return f"{self.season} {self.kind}"
