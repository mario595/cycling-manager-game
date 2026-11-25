"""Youth triage (#34): the squad spell, graduation, and the two decisions a
manager makes about a young rider — promote them or throw them away.

A squad rider arrives through intake, develops for SPELL_WEEKS in-season weeks
and then *graduates*: they leave the squad and free their place, but they are
not on the senior roster either. They sit as a graduate for
GRADUATE_WINDOW_WEEKS, drawing no wage, training with nobody and racing
nothing, while the manager promotes them onto the roster, lists them on the
transfer market, or discards them. Do nothing and the window closes and they
go to the free-agent pool.

**A graduate is still linked to their squad, and told apart by
`graduated_at`.** "In the squad" is `development_squad IS NOT NULL AND
graduated_at IS NULL`; "graduate" is `development_squad IS NOT NULL AND
graduated_at IS NOT NULL`. Keeping the squad link is what keeps a graduate out
of every roster query, out of the wage bill and out of the free-agent pool for
free — `team` is null for both, and every roster-shaped query in the codebase
filters on it (riders/README.md, *Youth intake*). It also gives the owning
team (`development_squad.team`) without a second foreign key, which is what
`belongs_to` uses for the market.

`world/` decides *when* a spell ends and a window closes: it counts the
in-season weeks, which needs `schedule.`, and `riders/` may not import that
(AGENTS.md). So the week count is passed in by the caller and this module only
acts on the ids it is handed.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from django.db import transaction
from django.db.models import QuerySet

from .departures import record_departures
from .development_squad import LEVELS
from .field_level import current_field_factor
from .models import ENGINE_ATTRIBUTES, Departure, DevelopmentSquad, Rider
from .pricing import weekly_salary_for
from .services import attribute_ceilings, mark_team_change, weekly_deltas

#: In-season weeks a rider spends in the squad before graduating. Chosen so the
#: squad's place cap actually binds: arrivals come every four weeks, so a squad
#: at steady state holds about eight riders just after a batch, and a 14-week
#: spell means a Regional squad (6 places) loses roughly every other batch
#: while an Elite one (10) has two to spare. A shorter spell would let the
#: oldest riders always leave before the next batch arrived, and the cap would
#: never matter.
SPELL_WEEKS = 14

#: In-season weeks a graduate has to decide before the rider is released to
#: the free-agent pool. Between seasons it does not run, like nothing else.
GRADUATE_WINDOW_WEEKS = 2

#: Fraction of the remaining gap to its ceiling a squad rider closes each week,
#: on top of the ordinary age curve. Proportional to the gap, so the rider with
#: more room — a higher hidden potential — develops faster: watching the numbers
#: move is the only evidence of a ceiling the player is never shown.
SQUAD_GROWTH_FRACTION = 0.03

#: Stored points per attribute per week a squad rider gains whenever they are
#: below their ceiling at all, however small the remaining gap. This is what
#: delivers "every rider ends their spell better than they arrived": without
#: it the proportional term alone leaves a hopeless youth visibly flat, and the
#: age curve on its own leaves roughly 17 arrivals in 4,000 with no visible
#: gain at all.
SQUAD_MIN_WEEKLY_GAIN = 0.8


@dataclass(frozen=True)
class SquadClosure:
    """What closing a squad did to the riders inside it: how many were
    discarded outright, and which graduates went to the free-agent pool."""

    discarded: int
    released: list[int]


class TriageError(Exception):
    """Base class for a triage action that cannot proceed."""


class NotYourProspect(TriageError):
    """That rider is in nobody's squad — not this team's, and not one of its
    graduates."""


class RosterFull(TriageError):
    """Promotion would put the team over the roster cap."""


class ProspectListed(TriageError):
    """That rider is currently listed on the transfer market. Raised by the
    caller's injected `check`, not here — `riders/` cannot see auctions."""


def in_squad(squad: DevelopmentSquad) -> QuerySet[Rider]:
    """Riders currently developing in `squad` — linked to it and not yet
    graduated. These are the only ones that count against its places."""
    return Rider.objects.filter(development_squad=squad, graduated_at__isnull=True)


def graduates(squad: DevelopmentSquad) -> QuerySet[Rider]:
    """Riders who have finished their spell in `squad` and are waiting for the
    manager to decide. They hold no place."""
    return Rider.objects.filter(development_squad=squad, graduated_at__isnull=False)


def free_places(squad: DevelopmentSquad) -> int:
    """How many riders `squad` can still take in, floored at zero.

    Graduates are excluded by construction: they have left the squad and their
    place, which is the whole point of graduating them rather than deleting
    them.
    """
    return max(0, LEVELS[squad.level].places - in_squad(squad).count())


def belongs_to(rider: Rider, team) -> bool:
    """Whether `team` may act on `rider` as its property — the ownership test
    the transfer market uses.

    True for a rider on the senior roster, and for a *graduate* of `team`'s
    squad, who reaches `team` through `development_squad.team` rather than
    through `team`. False for a rider still in the squad: the spec only lets a
    manager sell a graduate, because selling someone who has not finished
    their spell would let a squad be emptied for a profit rather than by a
    decision.
    """
    if rider.team_id == team.pk:
        return True
    if rider.development_squad_id is None or rider.graduated_at is None:
        return False
    return rider.development_squad.team_id == team.pk


def lock_rider(rider_id: int) -> Rider | None:
    """`rider_id` locked for update, with their squad fetched, or None.

    **Public because `transfers/` needs it too** (#34): listing and resolving
    a graduate's auction both read the squad under the rider's lock, and both
    would hit the same Postgres error below if they spelled it out again.

    `of=("self",)` is load-bearing: `development_squad` is a nullable FK, so
    `select_related` on it produces a LEFT OUTER JOIN, and Postgres refuses
    `FOR UPDATE` on the nullable side of one. Naming the table narrows the
    lock to the rider row — which is what is actually being written here; the
    squad row is only read to answer "is this my prospect".
    """
    return (
        Rider.objects.select_for_update(of=("self",))
        .select_related("development_squad")
        .filter(pk=rider_id)
        .first()
    )


def _prospect_of(rider: Rider | None, team) -> bool:
    """Whether `rider` is one of `team`'s squad riders or graduates — the
    ownership test `promote` and `discard` share.

    Both actions are allowed on a rider still in the squad *and* on a
    graduate, so this deliberately does not use `belongs_to`: that one answers
    the narrower question the transfer market asks, where a manager may sell a
    graduate but not someone mid-spell.
    """
    if rider is None or rider.development_squad_id is None:
        return False
    return rider.development_squad.team_id == team.pk


def squad_development_deltas(rider: Rider) -> dict[str, float]:
    """One extra week of attribute movement for a rider in a development
    squad, on top of the ordinary age curve.

    Per attribute, with `gap = max(0, ceiling - current)` and
    `base = weekly_deltas(rider)[a]`, the total wanted this week is

        min(gap, max(base + gap * SQUAD_GROWTH_FRACTION,
                     SQUAD_MIN_WEEKLY_GAIN if gap > 0 else 0))

    and what is returned is that total minus `base`. Three clauses, each
    carrying one promise:

    - **Proportional to the gap**, because the ceiling comes from hidden
      `potential`. A rider with more room develops faster, so watching the
      numbers move is real evidence about a ceiling the player is never shown.
    - **The floor** is what makes "every rider ends better than they arrived"
      true. Without it the proportional term alone leaves a hopeless youth
      visibly flat — the age curve on its own leaves about 17 arrivals in
      4,000 with no visible gain over a spell at all.
    - **The `min(gap, ...)` cap** is what makes "no rider passes their hidden
      ceiling" true, however generous the floor is.

    Returns only the *extra*: `world.services._apply_training_week` adds it
    into the per-rider `extra_deltas` map alongside the trainer's, and
    `apply_weekly_growth` settles age curve, training and squad development
    through one `growth_debt`, so a week rounds once instead of three times.

    Never touches the database, so it can be simulated in memory against a
    seeded `random.Random` — which is how the constants were tuned.
    """
    ceilings = attribute_ceilings(rider)
    base = weekly_deltas(rider)
    extra: dict[str, float] = {}

    for name in ENGINE_ATTRIBUTES:
        gap = max(0.0, ceilings[name] - getattr(rider, name))
        floor = SQUAD_MIN_WEEKLY_GAIN if gap > 0 else 0.0
        total = min(gap, max(base[name] + gap * SQUAD_GROWTH_FRACTION, floor))
        extra[name] = total - base[name]

    return extra


def graduate(rider_ids: Iterable[int], *, at) -> int:
    """Stamp `graduated_at = at` on every one of `rider_ids` that is still in
    a squad and has not graduated already. Returns rows updated.

    One conditional UPDATE whose WHERE re-checks both conditions, which is what
    makes it safe against a concurrent promote or discard — the same shape
    `riders.services.retire_riders` uses. A rider promoted or thrown away in
    the meantime is silently skipped, never an error: the tick does not care
    which of the two happened, only that it is no longer a squad rider.
    """
    return Rider.objects.filter(
        pk__in=list(rider_ids),
        development_squad__isnull=False,
        graduated_at__isnull=True,
    ).update(graduated_at=at)


def release_graduates(rider_ids: Iterable[int], *, at, record: bool) -> list[int]:
    """Send the graduates among `rider_ids` to the free-agent pool. Returns
    the ids actually released.

    Stamps `unattached_since = at` **before** clearing `development_squad`, in
    that order and under the rows' lock. Deleting or unlinking first would let
    a released graduate reach the pool with no stamp, and a free agent with a
    null `unattached_since` is never treated as long-unattached by the pool's
    expiry rule (transfers/README.md, *Free agents*) — they would sit in the
    market forever. Every path out of a squad goes through here for that
    reason: the window closing, an unsold auction, and closing the squad.

    Riders that are not graduates are ignored rather than refused: this is
    called with candidate ids from a tick, where the only thing to do about a
    rider who has already gone is nothing.

    **It opens its own transaction**, because one of its three callers — the
    tick's window step — has none to give it, and `select_for_update` outside
    a transaction raises rather than quietly doing nothing. Every test calls it
    inside the transaction pytest-django wraps a test in, which is how this
    survived them and was found by ticking a seeded world (plan's
    Verification): the first graduate whose window expired took the tick down
    with it. It also puts the stamp and the unlink in one transaction, so no
    reader can see a released graduate still pointing at a squad — or the
    reverse, a pool rider with no stamp, which the expiry rule never reclaims.

    **`record` has no default, on purpose** (#162): the window closing and an
    unsold auction happen while the manager is away, so they pass `True` and
    each released graduate gets a `released` departure against the squad's
    team; closing the squad is the manager's own act and passes `False`.
    Making every caller say which keeps a future one from recording, or
    staying silent, by accident.
    """
    with transaction.atomic():
        released = list(
            Rider.objects.select_for_update(of=("self",))
            .select_related("development_squad")
            .filter(
                pk__in=list(rider_ids),
                development_squad__isnull=False,
                graduated_at__isnull=False,
            )
        )
        if not released:
            return []
        if record:
            # Before the unlink: afterwards nothing says whose squad it was.
            record_departures(
                released,
                team_by_rider={
                    rider.pk: rider.development_squad.team_id for rider in released
                },
                kind=Departure.Kind.RELEASED,
                at=at,
            )
        mark_team_change(released, team_now=None, at=at)
        Rider.objects.filter(pk__in=[rider.pk for rider in released]).update(
            development_squad=None,
        )
        return [rider.pk for rider in released]


def promote(team, rider_id: int, *, at, roster_cap: int) -> Rider:
    """Move a squad rider or a graduate onto `team`'s senior roster.

    **The roster cap arrives as an argument, not as a constant.** It lives in
    `transfers/` and `riders/` may not import that; `api/` passes
    `transfers.services.ROSTER_CAP`. Promotion is not a market move, so it
    belongs here rather than there.

    Two details are the reason this is written out rather than left to the
    caller. `team` and `development_squad` are cleared in **one** `save()`,
    because `rider_not_on_roster_and_in_squad` is checked per statement and
    two saves would put a rider on the roster and in the squad at once for the
    length of one round trip. And the cap is counted under the rider's own row
    lock, an accepted narrow race for the same reason `sign_free_agent`
    accepts it: two simultaneous promotions can both pass and land the team at
    the cap plus one.

    The wage starts at the formula's value right now (`weekly_salary_for`) and
    is then frozen until the next season close like everyone else's, and
    `joined_team_at` is stamped by `mark_team_change` — which bulk-updates it,
    so it is deliberately not in `update_fields`.
    """
    with transaction.atomic():
        rider = lock_rider(rider_id)
        if not _prospect_of(rider, team):
            raise NotYourProspect("That rider is not in your development squad.")

        if Rider.objects.filter(team=team).count() >= roster_cap:
            raise RosterFull(f"Your team already has {roster_cap} riders.")

        rider.team = team
        rider.development_squad = None
        rider.weekly_salary = weekly_salary_for(rider, current_field_factor())
        mark_team_change([rider], team_now=team, at=at)
        rider.save(
            update_fields=[
                "team", "development_squad", "weekly_salary", "updated_at",
            ],
        )
    return rider


def discard(team, rider_id: int, *, check: Callable[[Rider], None] | None = None) -> None:
    """Delete one of `team`'s squad riders or graduates outright. The rider
    leaves the game — they do not go to the free-agent pool.

    `check` is an injected guard run while the rider is locked but before the
    delete. `api/` passes one that refuses a rider with an open auction,
    because `riders/` cannot see auctions and deleting a listed rider would
    cascade their auction and its whole bid history away.

    A plain `delete()` is safe here, and the precondition is asserted in
    `riders/tests/test_youth_triage.py` rather than guarded in code: a squad
    rider has never raced and cannot have a `RaceResult` or a `RaceSquadRider`,
    so their only dependents are `RiderAttributeSnapshot` rows, which cascade.
"""
    with transaction.atomic():
        rider = lock_rider(rider_id)
        if not _prospect_of(rider, team):
            raise NotYourProspect("That rider is not in your development squad.")

        if check is not None:
            check(rider)

        rider.delete()