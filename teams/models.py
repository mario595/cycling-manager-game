from __future__ import annotations

from django.core.validators import RegexValidator
from django.db import models

from core.models import TimeStampedModel

#: The race player renders teams by a 3-letter uppercase code and a colour;
#: see `race_player/README.md`. Validated here so a bad code can never reach
#: the log writer.
team_code_validator = RegexValidator(
    r"^[A-Z]{3}$",
    "Team code must be exactly three uppercase letters.",
)

hex_colour_validator = RegexValidator(
    r"^#[0-9A-Fa-f]{6}$",
    "Colour must be a hex value like #1A2B3C.",
)


class Team(TimeStampedModel):
    """A cycling team, managed by a player or by the AI.

    A team with no `manager` is AI-controlled. That is the normal state for
    most teams in a world — human managers are the minority — so the field is
    nullable rather than the relationship being mandatory.
    """

    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(
        max_length=3,
        validators=[team_code_validator],
        help_text=(
            "Three-letter TV-style abbreviation, e.g. 'MOV'. Deliberately "
            "not unique — a code is a display label, not an identity. Two "
            "teams may share one; disambiguating them within a Group is "
            "#56, not this field. See teams/README.md, Codes are not unique."
        ),
    )

    manager = models.OneToOneField(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="team",
        help_text="Null means the team is AI-controlled.",
    )

    primary_colour = models.CharField(
        max_length=7,
        default="#1E88E5",
        validators=[hex_colour_validator],
        help_text="Jersey colour used for rider markers in the race player.",
    )
    secondary_colour = models.CharField(
        max_length=7,
        default="#FFFFFF",
        validators=[hex_colour_validator],
    )

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.code})"

    @property
    def is_ai_controlled(self) -> bool:
        return self.manager_id is None
