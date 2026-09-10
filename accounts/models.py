from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """A player account.

    Deliberately thin for now. It exists from the first migration because
    swapping `AUTH_USER_MODEL` after migrations have been applied is painful
    in Django, and we know player-specific fields are coming.

    A user manages at most one team per game world; that link lives on
    `teams.Team.manager`, not here, so the team side owns the relationship.
    """

    display_name = models.CharField(
        max_length=50,
        blank=True,
        help_text="Public name shown to other managers. Falls back to username.",
    )

    def __str__(self) -> str:
        return self.display_name or self.username
