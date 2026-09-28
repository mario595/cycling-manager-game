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


class MarkerPoints(TimeStampedModel):
    """One team's points award for one sprint marker.

    Frozen at the moment the race is scored — see
    competitions/services.py, score_sprints, and competitions/README.md,
    *Sprint points*. Not recalculated if the points table changes later.

    `rider` is SET_NULL rather than CASCADE: the points a team scored are
    the record, and must survive a rider being deleted even though raced
    riders are not deleted today (#104).
    """

    marker = models.ForeignKey(
        "racing.RaceMarker", on_delete=models.CASCADE, related_name="points",
    )
    team = models.ForeignKey(
        "teams.Team", on_delete=models.CASCADE, related_name="marker_points",
    )
    rider = models.ForeignKey(
        "riders.Rider", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="marker_points",
    )
    position = models.PositiveSmallIntegerField(
        help_text="The scoring rider's crossing position at the marker, 1-5.",
    )
    points = models.PositiveSmallIntegerField(
        help_text="What the position was worth at the time it was awarded.",
    )

    class Meta:
        ordering = ["marker", "position"]
        constraints = [
            models.UniqueConstraint(
                fields=["marker", "team"], name="one_points_row_per_team_per_marker",
            ),
        ]
        indexes = [
            models.Index(fields=["team", "marker"], name="markerpoints_team_marker_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.team} scored {self.points} at {self.marker}"
