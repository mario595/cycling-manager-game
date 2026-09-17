from __future__ import annotations

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.models import TimeStampedModel
from riders.models import ENGINE_ATTRIBUTES, Rider


def _skill_field(help_text: str) -> models.PositiveSmallIntegerField:
    """A 1-100 trainer skill, validated the same way a rider's attributes
    are — see riders/models.py, _attribute_field. Defined locally rather
    than importing that helper: it is private to riders/models.py and its
    docstring ties it to the engine."""
    return models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(100)],
        help_text=help_text,
    )


class Trainer(TimeStampedModel):
    """A hireable trainer, in the shared pool or filling one team's slot.

    The five skills deliberately share ENGINE_ATTRIBUTES' names — a
    trainer's speciality is one of a rider's five engine attributes,
    because weekly training (#36) maps its focus selection onto one of
    them. Stored 1-100 like a rider's own attributes and shown 0-10
    through the same riders.display.to_display_scale mapping; see
    staff/README.md, *Stored 1-100, displayed 0-10*.
    """

    name = models.CharField(max_length=100)
    nationality = models.CharField(
        max_length=2,
        choices=Rider.Nationality.choices,
        default=Rider.Nationality.SPAIN,
    )

    team = models.OneToOneField(
        "teams.Team",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="trainer",
        help_text="Null means unemployed — in the shared hiring pool.",
    )

    climb = _skill_field("How much faster a rider improves at climbing.")
    sprint = _skill_field("How much faster a rider improves at sprinting.")
    flat = _skill_field("How much faster a rider improves on the flat.")
    resistance = _skill_field("How much faster a rider improves resistance.")
    positioning = _skill_field("How much faster a rider improves positioning.")

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @property
    def speciality(self) -> str:
        """The skill this trainer is best at. Derived, never stored —
        generation guarantees exactly one maximum (staff/generation.py), so
        `max` here never has a tie to break."""
        return max(ENGINE_ATTRIBUTES, key=lambda name: getattr(self, name))


#: The five attributes a training focus can pick from, as (value, label)
#: choices — built here so the attribute names appear once.
ATTRIBUTE_CHOICES = [(name, name.title()) for name in ENGINE_ATTRIBUTES]
#: The focus a team falls back to before they have ever chosen one.
DEFAULT_FOCUS = ENGINE_ATTRIBUTES[0]


class TrainingFocus(TimeStampedModel):
    """A team's current weekly training focus — one of the five attributes.

    Keyed to the team, not to the Trainer filling its slot: a focus is a
    property of a team's training programme, and firing a trainer to hire
    another must not silently reset what the team was working on. See
    specs/weekly-training-focus-plan.md, Design decision 5. The row is
    created on demand (get_or_create); a team that has never chosen has no
    row and is treated as DEFAULT_FOCUS.
    """

    team = models.OneToOneField(
        "teams.Team",
        on_delete=models.CASCADE,
        related_name="training_focus",
        help_text="One focus per team. Deleted with the team.",
    )
    attribute = models.CharField(
        max_length=12,
        choices=ATTRIBUTE_CHOICES,
        default=DEFAULT_FOCUS,
        help_text="The attribute this week's training targets.",
    )

    def __str__(self) -> str:
        return f"{self.team} trains {self.attribute}"


class TrainingWeekReport(TimeStampedModel):
    """What a week's training did for one team, for the Training screen.

    Holds the riders whose *displayed* (0-10) value moved at the rollover —
    the stored attribute after the fact cannot tell you what it was before,
    so the snapshot is written when the training happens. `week` is a string
    reference so staff/models.py needs no import of schedule/ (AGENTS.md);
    see staff/README.md, *What `staff/` may import*.
    """

    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.CASCADE,
        related_name="training_reports",
    )
    week = models.ForeignKey(
        "schedule.Week",
        on_delete=models.CASCADE,
        related_name="training_reports",
    )
    attribute = models.CharField(
        max_length=12,
        blank=True,
        default="",
        help_text="The focus applied that week. Empty when the team had no trainer.",
    )
    changes = models.JSONField(
        default=list,
        help_text=(
            '[{"rider_id", "rider_name", "attribute", "from", "to"}] on the 0-10 '
            "display scale. An empty list is normal."
        ),
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["team", "week"], name="one_training_report_per_team_per_week",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.team}, {self.week}"
