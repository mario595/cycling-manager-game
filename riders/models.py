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
    `injury_proneness`, `training_affinity`, `growth_debt`,
    `recovery_rate`) are never serialized — see riders/README.md.
    `potential`, `peak_age` and `decline_rate` drive weekly growth and
    decline (#58); `injury_proneness` and `training_affinity` remain
    inert until #41 (injuries) and #36 (training) each start reading
    one. `freshness` is visible (0-10 via to_display_scale, like any
    attribute) but its recovery rate is not — the value is what the
    player acts on; how fast it climbs back is learned by watching it.
    """

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
        help_text="Advanced by one for every rider when a season closes (#58).",
    )
    freshness = models.PositiveSmallIntegerField(
        default=100,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text=(
            "Visible (0-10 via to_display_scale). Falls RACE_FRESHNESS_COST "
            "when a rider finishes a race, recovers weekly for rested riders. "
            "See riders/services.py."
        ),
    )
    weekly_salary = models.PositiveIntegerField(
        default=1200,
        validators=[MinValueValidator(1)],
        help_text=(
            "Visible, exact whole credits (never mapped through "
            "to_display_scale). Set once at creation by riders.pricing."
            "weekly_salary_for and frozen until a season boundary decides "
            "otherwise (#26) — never recomputed as attributes move. The "
            "default here is only a migration/test convenience, not a real "
            "rider's price."
        ),
    )

    # --- Team-membership timing (game time, not wall clock) ---
    joined_team_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Game time this rider's team was last set to a non-null value — "
            "by generation, a team claim, or a free-agent signing. Null for a "
            "rider that has never had joined_team_at stamped (pre-migration "
            "data) or is currently unattached and was never tracked. Used to "
            "gate the free claim-release cooldown (transfers/README.md)."
        ),
    )
    unattached_since = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Game time this rider's team last became null — by a team claim "
            "releasing its old roster, or a manager releasing them to the "
            "free agent pool. Null while on a team. Drives pool expiry "
            "(transfers/README.md)."
        ),
    )

    # --- Hidden, between-race traits (never serialized — see class docstring) ---
    potential = models.PositiveSmallIntegerField(
        default=70,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Hidden. Scaled per attribute by speciality shape to set the ceiling growth (#58) approaches.",
    )
    peak_age = models.PositiveSmallIntegerField(
        default=27,
        validators=[MinValueValidator(22), MaxValueValidator(34)],
        help_text="Hidden. Below this age attributes grow toward potential; at or above it they decline (#58).",
    )
    decline_rate = models.PositiveSmallIntegerField(
        default=50,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text="Hidden. Higher falls away faster past peak_age (#58).",
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
    recovery_rate = models.PositiveSmallIntegerField(
        default=50,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text=(
            "Hidden. Maps onto how much freshness a rested rider regains each "
            "week (RECOVERY_MIN..RECOVERY_MAX in riders/services.py). Never "
            "serialized — the player infers it from the visible freshness "
            "moving. See riders/README.md, Visible vs hidden."
        ),
    )
    growth_debt = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Hidden. {attribute_name: float} over ENGINE_ATTRIBUTES — fractional "
            "weekly growth/decline (#58) not yet large enough to move the stored "
            "integer attribute. A missing key reads as 0.0. Empty until the first "
            "week of growth runs, so blank is this field's normal starting state."
        ),
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class RiderAttributeSnapshot(TimeStampedModel):
    """One rider's five displayed (0-10) attributes at a point in time.

    Written at creation (`week=None`, the baseline) and thereafter only in a
    week where at least one displayed value moved — see riders/services.py,
    record_initial_snapshots and record_week_snapshots. Values here are the
    0-10 scale a player sees, never the stored 1-100 value: recording the
    finer value would leak growth the display scale is designed to hide
    (riders/README.md, *Display scale*).

    `week` is a string reference so this app needs no import of `schedule/`
    (AGENTS.md) — the same pattern `staff.TrainingWeekReport.week` uses.
    """

    rider = models.ForeignKey(
        Rider, on_delete=models.CASCADE, related_name="attribute_snapshots",
    )
    week = models.ForeignKey(
        "schedule.Week",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rider_attribute_snapshots",
        help_text="Null means the baseline snapshot taken at creation.",
    )
    climb = models.PositiveSmallIntegerField()
    sprint = models.PositiveSmallIntegerField()
    flat = models.PositiveSmallIntegerField()
    resistance = models.PositiveSmallIntegerField()
    positioning = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["rider", "week"], name="one_snapshot_per_rider_per_week",
            ),
        ]
        indexes = [models.Index(fields=["rider", "created_at"])]

    def __str__(self) -> str:
        return f"{self.rider} @ {self.week or 'baseline'}"
