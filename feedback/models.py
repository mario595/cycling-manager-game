"""A beta tester's report of a problem, with the context it was sent in.

Both foreign keys are string references, so this module imports neither
`accounts/` nor `teams/` — see feedback/README.md, *What `feedback/` may
import*.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class Report(models.Model):
    """One report. What the reporter wrote and the context captured with it
    never change after creation; only the triage fields do.

    The context columns are a **snapshot**: `team_name`, `season_number` and
    `week_number` record where the reporter was when they sent it, and are
    never recomputed from the author's current team or the current week —
    see feedback/README.md, *Context is a snapshot*.
    """

    class Category(models.TextChoices):
        BUG = "bug", "Bug"
        LOOKS_WRONG = "looks_wrong", "Looks wrong"
        BALANCE = "balance", "Balance"
        SUGGESTION = "suggestion", "Suggestion"

    class Status(models.TextChoices):
        NEW = "new", "New"
        TRIAGED = "triaged", "Triaged"
        DISMISSED = "dismissed", "Dismissed"

    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="reports",
    )
    category = models.CharField(max_length=20, choices=Category.choices)
    # No database limit: the serializer refuses over-long text, so the limit
    # can move without a migration.
    text = models.TextField()
    # What the caller says it was looking at: the SPA's route, or the
    # endpoint an agent was calling. Optional.
    location = models.CharField(max_length=300, blank=True, default="")

    # The team the author managed when they sent it. SET_NULL keeps the
    # report if the team row is ever deleted; team_name keeps the name it had.
    #
    # db_constraint=False is load-bearing: world_setup.wipe_world truncates
    # teams_team with CASCADE, and Postgres's TRUNCATE CASCADE empties every
    # table holding a foreign-key *constraint* into a truncated one, rows or
    # no rows. With the constraint, a staging reset would delete every
    # report. wipe_world clears this column first, so a report never points
    # at the unrelated team that later reuses the id (RESTART IDENTITY).
    # See feedback/README.md, *Reports outlive a world reset*.
    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        db_constraint=False,
    )
    team_name = models.CharField(max_length=100, blank=True, default="")
    # Empty off-season and before the first season is declared.
    season_number = models.PositiveIntegerField(null=True, blank=True)
    week_number = models.PositiveIntegerField(null=True, blank=True)

    # Two clocks, deliberately: the game's time (world.services.now(), far
    # ahead of the wall clock on staging) and the real time it was sent.
    game_time = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    github_issue_url = models.URLField(blank=True, default="")
    # Staff only — never serialized to the reporter.
    triage_note = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["author", "created_at"])]

    def __str__(self) -> str:
        return f"#{self.pk} {self.get_category_display()}: {self.text[:60]}"
