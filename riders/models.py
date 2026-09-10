from __future__ import annotations

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.models import TimeStampedModel

#: Attribute names shared with `race_engine.models.RiderAttributes`.
#: The engine is the source of truth for what these mean; see
#: `race_engine/README.md`. Kept as a tuple so the adapter in `racing/` can
#: iterate it instead of hard-coding the list in two places.
ENGINE_ATTRIBUTES = ("climb", "sprint", "flat", "resistance", "positioning")


def _attribute_field(help_text: str) -> models.PositiveSmallIntegerField:
    """A 1-100 engine attribute, validated the same way the engine validates."""
    return models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text=help_text,
    )


class Rider(TimeStampedModel):
    """A rider as persisted by the game.

    This mirrors `race_engine.models.Rider` but is **not** the same class and
    must never become one. The engine works on plain dataclasses so that it
    stays fast, testable without a database, and independent of Django. The
    translation between the two lives in `racing/adapters.py` — nothing else
    should convert between them.

    Fields here that the engine knows nothing about (age, form, contracts)
    are game-layer concerns; they influence a race only by being folded into
    the attributes handed to the engine at race time.
    """

    class Role(models.TextChoices):
        LEADER = "leader", "Leader"
        SUPPORT = "support", "Support"

    name = models.CharField(max_length=100)

    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="riders",
        help_text="Null means a free agent — no team.",
    )
    role = models.CharField(
        max_length=10,
        choices=Role.choices,
        default=Role.LEADER,
        help_text="Matches the engine's role. The engine reads this, it does not derive it.",
    )

    # --- Engine attributes (1-100) ---
    climb = _attribute_field("Speed uphill and ability to attack climbs.")
    sprint = _attribute_field("Top-end finishing power; also blends into descending speed.")
    flat = _attribute_field("Speed on flat terrain.")
    resistance = _attribute_field("Fatigue tolerance; slows stamina drain.")
    positioning = _attribute_field("Draft/shelter skill.")

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
