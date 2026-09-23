from __future__ import annotations

from django.db import transaction

from riders.generation import generate_roster
from riders.models import Rider

from .models import ManagerialSpell, Team

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


class ReleaseError(Exception):
    """Base class for a release that cannot proceed."""


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
        team.managed_since = at
        team.name = name
        team.code = code
        team.full_clean(exclude=["manager"])
        team.save(update_fields=["manager", "managed_since", "name", "code", "updated_at"])

        team.riders.update(team=None)
        Rider.objects.bulk_create(generate_roster(roster_size, team=team))

        # Imported here, not at module scope: teams/ must not import
        # economy/ at import time (AGENTS.md's dependency direction). Same
        # rule and reason as seed_teams.py importing racing.models inside
        # handle().
        from economy.services import reset_fanbase, reset_to_starting_balance, void_sponsorship
        reset_to_starting_balance(team, at=at)
        reset_fanbase(team, at=at)
        void_sponsorship(team, at=at)
    return team


def release_team(team: Team, *, reason: str, at) -> ManagerialSpell | None:
    """Return `team` to the unmanaged pool, recording the spell that just
    ended. Returns None if the team already has no manager.

    Clears Team.manager and Team.managed_since and writes one
    ManagerialSpell. Deliberately touches nothing else — not the roster, not
    the ledger, not the fanbase, not the sponsorship. Release is not claim's
    inverse: claim_team resets the present on the NEXT claim, and a released
    team must be indistinguishable from one that was never managed (#44).

    `at` is the game time the release is recorded at, supplied by the caller
    (world.services.now()) because teams/ must not import world/ — same rule
    as claim_team's `at`.

    Uses select_for_update() without skip_locked, unlike claim_team: this
    acts on one named team rather than shopping for any free one, so it must
    not silently no-op just because another transaction holds the row.
    """
    with transaction.atomic():
        locked = Team.objects.select_for_update().filter(pk=team.pk).first()
        if locked is None or locked.manager_id is None:
            return None

        spell = ManagerialSpell.objects.create(
            manager_id=locked.manager_id,
            team=locked,
            team_name=locked.name,
            team_code=locked.code,
            started_at=locked.managed_since,
            ended_at=at,
            reason=reason,
        )
        locked.manager = None
        locked.managed_since = None
        locked.save(update_fields=["manager", "managed_since", "updated_at"])
    return spell
