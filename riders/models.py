from __future__ import annotations

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.models import TimeStampedModel

#: Attribute names shared with `race_engine.models.RiderAttributes`.
#: The engine is the source of truth for what these mean; see
#: `race_engine/README.md`. Kept as a tuple so the adapter in `racing/` can
#: iterate it instead of hard-coding the list in two places.
#:
#: These are deliberately the only fields the engine ever sees. Everything
#: else on this model — speciality, build, age, and the hidden traits below —
#: is a game-layer concern the engine does not know exists; see
#: specs/rider-attributes.md, *The engine boundary*.
ENGINE_ATTRIBUTES = ("climb", "sprint", "flat", "resistance", "positioning")

#: The player sees ratings on this scale; the database stores 1-100. See
#: riders/display.py, to_display_scale.
DISPLAY_MAX = 10


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

    Fields here that the engine knows nothing about (speciality, build, age,
    the hidden traits) are game-layer concerns; they influence a race only by
    being folded into the attributes handed to the engine at race time.

    The hidden traits (`potential`, `peak_age`, `decline_rate`,
    `injury_proneness`, `training_affinity`) are stored but inert as of
    #57 — nothing reads them yet. They exist so a rider generated today does
    not need regenerating when #58 (growth/decline), #41 (injuries) and #36
    (training) each start reading one. **Never add them to a serializer** —
    see riders/README.md.
    """

    class Role(models.TextChoices):
        LEADER = "leader", "Leader"
        SUPPORT = "support", "Support"

    class Speciality(models.TextChoices):
        CLIMBER = "climber", "Climber"
        SPRINTER = "sprinter", "Sprinter"
        ROULEUR = "rouleur", "Rouleur"
        PUNCHEUR = "puncheur", "Puncheur"
        DOMESTIQUE = "domestique", "Domestique"

    class Nationality(models.TextChoices):
        SPAIN = "ES", "Spain"

    name = models.CharField(max_length=100)
    nationality = models.CharField(
        max_length=2,
        choices=Nationality.choices,
        default=Nationality.SPAIN,
        help_text=(
            "Only Spain exists today; the choices class exists so a second "
            "country is a choices-list and name-pool edit, not a migration."
        ),
    )

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

    # --- Visible, between-race attributes ---
    speciality = models.CharField(
        max_length=12,
        choices=Speciality.choices,
        default=Speciality.ROULEUR,
        help_text="Assigned at creation, never changes. Not read by the engine.",
    )
    height_cm = models.PositiveSmallIntegerField(
        default=178,
        validators=[MinValueValidator(150), MaxValueValidator(210)],
        help_text="Fixed for life, generated consistent with speciality.",
    )
    weight_kg = models.PositiveSmallIntegerField(
        default=70,
        validators=[MinValueValidator(45), MaxValueValidator(100)],
        help_text="Fixed for life, generated consistent with speciality.",
    )
    age = models.PositiveSmallIntegerField(
        default=25,
        validators=[MinValueValidator(18), MaxValueValidator(40)],
        help_text="Static as of #57. Advanced once per season by #58.",
    )

    # --- Hidden, between-race traits (never serialized — see class docstring) ---
    potential = models.PositiveSmallIntegerField(
        default=70,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Hidden. The ceiling attributes grow toward once #58 lands.",
    )
    peak_age = models.PositiveSmallIntegerField(
        default=27,
        validators=[MinValueValidator(22), MaxValueValidator(34)],
        help_text="Hidden. When growth turns to decline, once #58 lands.",
    )
    decline_rate = models.PositiveSmallIntegerField(
        default=50,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Hidden. Higher falls away faster past peak_age, once #58 lands.",
    )
    injury_proneness = models.PositiveSmallIntegerField(
        default=50,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Hidden. Read by injuries, once #41 lands.",
    )
    training_affinity = models.JSONField(
        default=dict,
        help_text=(
            "Hidden. {attribute_name: weight} over ENGINE_ATTRIBUTES, read by "
            "weekly training once #36 lands."
        ),
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name
