from __future__ import annotations

from django.db import transaction

from riders.generation import generate_roster
from riders.models import Rider

from .models import Team

#: Riders generated for a newly claimed team, matching
#: riders/management/commands/reset_riders.py's DEFAULT_RIDERS_PER_TEAM. Not
#: imported from there — a management command is an entry point, not a
#: library.
ROSTER_SIZE = 12


class ClaimError(Exception):
    """Base class for a claim that cannot proceed."""


class NoTeamAvailable(ClaimError):
    """There is no unmanaged team left to claim."""


class AlreadyManaging(ClaimError):
    """Raised by callers, not by claim_team itself — see its docstring."""


def claim_team(user, *, name: str, code: str, roster_size: int = ROSTER_SIZE, at) -> Team:
    """Assign an unmanaged team to `user`, rename it, release its riders and
    give it a freshly generated roster. One transaction: a half-claimed team
    (renamed but with no roster) must never be observable.

    Does not check whether `user` already manages a team — Team.manager is a
    OneToOneField, so a second claim raises IntegrityError, and the caller
    (api.views.ClaimTeamView) checks first via team_for() so the happy path
    never relies on that exception.

    `at` is the game time the takeover is recorded at, handed on to
    economy.services.reset_to_starting_balance — the caller (api/, `teams/`'s
    seed command) passes `world.services.now()` itself. teams/'s library code
    must not import world/ (AGENTS.md), so the caller supplies it, the same
    way schedule/services.py's callers do.
    """
    with transaction.atomic():
        team = (
            Team.objects.select_for_update(skip_locked=True)
            .filter(manager__isnull=True)
            .order_by("pk")
            .first()
        )
        if team is None:
            raise NoTeamAvailable("There are no teams available to claim.")

        team.manager = user
        team.name = name
        team.code = code
        team.full_clean(exclude=["manager"])
        team.save(update_fields=["manager", "name", "code", "updated_at"])

        team.riders.update(team=None)
        Rider.objects.bulk_create(generate_roster(roster_size, team=team))

        # Imported here, not at module scope: teams/ must not import
        # economy/ at import time (AGENTS.md's dependency direction). Same
        # rule and reason as seed_teams.py importing racing.models inside
        # handle().
        from economy.services import reset_to_starting_balance
        reset_to_starting_balance(team, at=at)
    return team
