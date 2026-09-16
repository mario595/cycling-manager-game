from __future__ import annotations

from django.db import models

from core.models import TimeStampedModel


class RacePoints(TimeStampedModel):
    """One team's points award for one race.

    Frozen at the moment the race is scored — see
    competitions/services.py, score_race, and competitions/README.md,
    *The points table*. Not recalculated if the points table changes later.
    """

    race = models.ForeignKey(
        "racing.Race", on_delete=models.CASCADE, related_name="points",
    )
    team = models.ForeignKey(
        "teams.Team", on_delete=models.CASCADE, related_name="race_points",
    )
    position = models.PositiveSmallIntegerField(
        help_text="The team's best classified finisher's position, 1-10.",
    )
    points = models.PositiveSmallIntegerField(
        help_text="What the position was worth at the time it was awarded.",
    )

    class Meta:
        ordering = ["race", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["race", "team"], name="one_points_row_per_team_per_race",
            ),
        ]
        indexes = [
            models.Index(fields=["team", "race"], name="points_team_race_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.team} scored {self.points} in {self.race}"
