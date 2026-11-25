from __future__ import annotations

import statistics
from collections import defaultdict

from django.db import transaction

from riders.development_squad import close_squad
from riders.field_level import current_field_factor
from riders.generation import generate_roster
from riders.models import ENGINE_ATTRIBUTES, Rider
from riders.pricing import strength
from riders.services import mark_team_change, record_initial_snapshots

from .models import ManagerialSpell, Team

#: The size a newly claimed team's roster is topped up to, matching
#: riders/management/commands/reset_riders.py's DEFAULT_RIDERS_PER_TEAM. Not
#: imported from there — a management command is an entry point, not a
#: library.
ROSTER_SIZE = 12

#: How many of a team's best riders its squad strength averages: two squads'
#: worth, enough to cover a rotation and a stage race's fatigue. Missing places
#: count as zero, so a stripped roster ranks as weak (#156,
#: specs/archive/claimed-team-keeps-its-riders-plan.md, Design decision 1).
SQUAD_STRENGTH_DEPTH = 8


class ClaimError(Exception):
    """Base class for a claim that cannot proceed."""


class NoTeamAvailable(ClaimError):
    """There is no unmanaged team left to claim."""


class AlreadyManaging(ClaimError):
    """Raised by callers, not by claim_team itself — see its docstring."""


class ReleaseError(Exception):
    """Base class for a release that cannot proceed."""


def squad_strength(riders: list[Rider]) -> float:
    """The mean strength (riders.pricing.strength) of the best
    SQUAD_STRENGTH_DEPTH riders in `riders`, a missing place counting as 0.

    Pure over a list, so it needs no database. This is how a claim judges
    "the middle of the field" (#156)."""
    best = sorted((strength(r) for r in riders), reverse=True)[:SQUAD_STRENGTH_DEPTH]
    return sum(best) / SQUAD_STRENGTH_DEPTH


def _claim_candidates() -> list[int]:
    """Unmanaged team pks, nearest the field's median squad strength first,
    pk breaking ties. The field is every team, managed or not. Reads only;
    locks nothing: claim_team locks the first candidate it can.

    One query for every team's riders, grouped here, rather than one per
    team."""
    teams = list(Team.objects.values_list("pk", "manager_id"))
    if not teams:
        return []
    by_team: dict[int, list[Rider]] = defaultdict(list)
    for rider in Rider.objects.filter(team__isnull=False).only(
        "team_id", "speciality", *ENGINE_ATTRIBUTES,
    ):
        by_team[rider.team_id].append(rider)
    scores = {pk: squad_strength(by_team[pk]) for pk, _ in teams}
    middle = statistics.median(scores.values())
    unmanaged = [pk for pk, manager_id in teams if manager_id is None]
    return sorted(unmanaged, key=lambda pk: (abs(scores[pk] - middle), pk))


def claim_team(user, *, name: str, code: str, roster_size: int = ROSTER_SIZE, at) -> Team:
    """Assign an unmanaged team to `user`, rename it and keep its riders,
    topping a roster under `roster_size` up with generated riders. One
    transaction: a half-claimed team must never be observable.

    The team handed over is the unmanaged one whose squad strength is
    nearest the middle of the whole field (#156), not the lowest pk: a
    claimant takes over the "average team" the economy is tuned for. Ties
    go to the lower pk.

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
        # Rank without a lock, then lock the first candidate still free.
        # skip_locked means a concurrent claimer moves on to the next one
        # instead of blocking, and the manager filter refuses a team claimed
        # since the ranking was read. Locking every unmanaged team up front
        # would serialise claims; locking the lowest pk was the old rule.
        team = None
        for pk in _claim_candidates():
            team = (
                Team.objects.select_for_update(skip_locked=True)
                .filter(pk=pk, manager__isnull=True)
                .first()
            )
            if team is not None:
                break
        if team is None:
            raise NoTeamAvailable("There are no teams available to claim.")

        team.manager = user
        team.managed_since = at
        team.name = name
        team.code = code
        team.full_clean(exclude=["manager"])
        team.save(update_fields=["manager", "managed_since", "name", "code", "updated_at"])

        # The squad comes with the team (#156). Re-stamp joined_team_at to the
        # claim instant anyway: the claim cooldown's free release
        # (transfers._claim_cooldown_exempt) recognises the claimed roster by
        # joined_team_at == managed_since. No new baseline snapshots: these
        # riders already have their history.
        kept = list(team.riders.all())
        mark_team_change(kept, team_now=team, at=at)

        # Fill only the gap. A roster above roster_size is never trimmed.
        missing = max(0, roster_size - len(kept))
        if missing:
            top_up = Rider.objects.bulk_create(generate_roster(
                missing, team=team, field_factor=current_field_factor(),
            ))
            mark_team_change(top_up, team_now=team, at=at)
            record_initial_snapshots(top_up)

        # After the roster write, before the lazy economy import
        # below. A claim is a takeover, and what the last manager left behind
        # does not carry over — a new manager must open their own squad and
        # pay their own opening fee. Closing is a row delete, so there is
        # nothing to refund or to void here (riders/README.md, *Development
        # squad*). release_team is deliberately NOT symmetric, per the spec's
        # *Decisions taken*: releasing hands the team back as it stands, squad
        # included, so a manager who quits leaves the squad they paid for.
        # Its riders are not: closing discards everyone still in the squad and
        # releases only the graduates to the free-agent pool (#33, #34).
        close_squad(team, at=at)

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
