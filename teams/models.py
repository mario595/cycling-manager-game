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
    managed_since = models.DateTimeField(
        null=True,
        blank=True,
        help_text=(
            "Game time the current manager claimed this team. Null when "
            "unmanaged, and for a team claimed before this field existed. "
            "Set by claim_team, cleared by release_team — see "
            "teams/README.md, Releasing a team."
        ),
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


class ManagerialSpell(TimeStampedModel):
    """A completed period during which one user managed one team.

    Written by `release_team` when the spell ends — see teams/README.md,
    *Managerial spells*. `team_name`/`team_code` are snapshotted at release
    rather than read live through `team`, because #46 lets the next claimer
    rename the team; a live read would silently rewrite an ex-manager's own
    history the moment a stranger renames it.
    """

    class Reason(models.TextChoices):
        INACTIVITY = "inactivity", "Manager inactive"
        INSOLVENCY = "insolvency", "Team insolvent"
        ADMIN = "admin", "Released by an operator"

    manager = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="managerial_spells",
        help_text="A deleted account's managerial history has no meaning.",
    )
    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="managerial_spells",
        help_text="Null if the team was later deleted (e.g. seed_teams --reset).",
    )
    team_name = models.CharField(
        max_length=100,
        help_text="The team's name at the moment of release. What is displayed.",
    )
    team_code = models.CharField(
        max_length=3,
        help_text="The team's code at the moment of release. What is displayed.",
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Game time the spell began, from Team.managed_since. Null "
        "for a team claimed before that field existed.",
    )
    ended_at = models.DateTimeField(help_text="Game time of the release.")
    reason = models.CharField(max_length=20, choices=Reason.choices)
    acknowledged_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Real time the ex-manager was shown the message. Null "
        "means not yet shown.",
    )

    class Meta:
        ordering = ["-ended_at"]
        indexes = [models.Index(fields=["manager", "acknowledged_at"])]

    def __str__(self) -> str:
        return f"{self.team_name} ({self.manager_id}, ended {self.ended_at})"
