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
