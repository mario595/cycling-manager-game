"""Simulating a race and recording its result.

`racing/` owns simulation; `world/` calls it — never the reverse (`AGENTS.md`
forbids `racing/` importing `world/`). `game_time` is therefore a parameter,
not read from the clock here.
"""

from __future__ import annotations

import logging
import tempfile
from datetime import datetime
from pathlib import Path

from django.core.files.base import ContentFile
from django.db import transaction

from riders.models import ENGINE_ATTRIBUTES, Rider
from teams.models import Team

from .adapters import run_race_via_adapter, to_engine_course, to_engine_rider, to_team_codes
from .models import SQUAD_SIZE, Race, RaceLog, RaceResult, RaceSquad, RaceSquadRider

logger = logging.getLogger(__name__)


class SquadError(ValueError):
    """An invalid squad: wrong size, a rider from another team, or not
    exactly one leader. Raised by set_squad and turned into a 400 by the
    API."""


def auto_pick_squad(team: Team) -> tuple[list[int], int]:
    """Four rider ids and the leader's id, chosen naively.

    By total engine attributes descending, then by pk ascending — the pk
    tiebreak is what makes this deterministic and so testable. The strongest
    rider leads. Deliberately course-blind: see specs/squad-selection.md,
    Out of scope, and #45.

    Raises SquadError if the team has fewer than four riders.
    """
    riders = list(team.riders.all())
    if len(riders) < SQUAD_SIZE:
        raise SquadError(
            f"{team} has only {len(riders)} riders; a squad needs {SQUAD_SIZE}"
        )

    ordered = sorted(
        riders,
        key=lambda r: (
            -sum(getattr(r, name) for name in ENGINE_ATTRIBUTES),
            r.pk,
        ),
    )
    picked = ordered[:SQUAD_SIZE]
    return [r.pk for r in picked], picked[0].pk


def previous_squad(team: Team, before: Race) -> tuple[list[int], int] | None:
    """The riders and leader from this team's most recent squad in a race
    starting before `before`, or None if there is not one.

    "Most recent" is by the race's starts_at, descending. Riders no longer
    on the team are dropped, so a squad short of four after filtering
    returns None and the caller falls back to auto_pick_squad.
    """
    squad = (
        RaceSquad.objects.filter(
            team=team, race__starts_at__isnull=False, race__starts_at__lt=before.starts_at,
        )
        .order_by("-race__starts_at")
        .prefetch_related("members__rider")
        .first()
    ) if before.starts_at else None
    if squad is None:
        return None

    members = [m for m in squad.members.all() if m.rider.team_id == team.pk]
    if len(members) != SQUAD_SIZE:
        return None

    leader = next((m.rider_id for m in members if m.is_leader), None)
    if leader is None:
        return None

    return [m.rider_id for m in members], leader


def suggested_squad(race: Race, team: Team) -> tuple[list[int], int]:
    """What to pre-fill a manager's screen with: their existing squad for
    this race if they have one, else their previous squad, else an
    auto-pick. Reads only; writes nothing."""
    existing = RaceSquad.objects.filter(race=race, team=team).prefetch_related("members").first()
    if existing is not None:
        members = list(existing.members.all())
        leader = next((m.rider_id for m in members if m.is_leader), None)
        if len(members) == SQUAD_SIZE and leader is not None:
            return [m.rider_id for m in members], leader

    fallback = previous_squad(team, race)
    if fallback is not None:
        return fallback

    return auto_pick_squad(team)


def _write_squad(
    race: Race, team: Team, rider_ids: list[int], leader_id: int, *, auto: bool,
) -> RaceSquad:
    """Validate and replace `team`'s squad for `race`, with no status check.

    set_squad adds the check that a race must still be SCHEDULED; this
    helper skips it deliberately, because ensure_squads (called from
    simulate_race) writes a squad after the tick has already flipped the
    race to RUNNING. Do not add a `force` flag to set_squad instead — a
    flag that disables the one rule protecting a started race is a flag
    someone will pass by mistake.
    """
    ids = list(dict.fromkeys(rider_ids))
    if len(ids) != len(rider_ids):
        raise SquadError("a rider cannot be entered twice")
    if len(ids) != SQUAD_SIZE:
        raise SquadError(f"a squad is exactly {SQUAD_SIZE} riders, got {len(ids)}")

    # filter(pk__in=ids, team=team) does the "on the team" check and the
    # "exists" check in one query — fetching by pk__in alone and comparing
    # rider.team_id afterwards is the version that misses a rider id that
    # does not exist at all.
    riders = list(Rider.objects.filter(pk__in=ids, team=team))
    if len(riders) != SQUAD_SIZE:
        raise SquadError("every rider in a squad must be on the team")
    if leader_id not in ids:
        raise SquadError("the leader must be one of the selected riders")

    with transaction.atomic():
        squad, _ = RaceSquad.objects.update_or_create(
            race=race, team=team, defaults={"is_auto_picked": auto},
        )
        squad.members.all().delete()
        RaceSquadRider.objects.bulk_create([
            RaceSquadRider(squad=squad, rider=r, is_leader=r.pk == leader_id)
            for r in riders
        ])
    return squad


def set_squad(race: Race, team: Team, rider_ids: list[int], leader_id: int) -> RaceSquad:
    """Replace `team`'s squad for `race`. The public writer — everything a
    manager does goes through here.

    Refuses a race that is not SCHEDULED, then delegates to _write_squad.
    Raises SquadError for that and for every validation failure below.
    """
    if race.status != Race.Status.SCHEDULED:
        raise SquadError(f"{race} has already started; its squad is fixed")
    return _write_squad(race, team, rider_ids, leader_id, auto=False)


def ensure_squads(race: Race) -> None:
    """Give every team with enough riders a squad for this race, if it has
    not got one. Called from simulate_race so a team whose manager never
    chose still starts — specs/squad-selection.md, in scope item 8.

    A team with fewer than SQUAD_SIZE riders is skipped with a warning, not
    an exception: that is a broken roster (see the spec's Rules and edge
    cases) and it must not stop every other team racing.
    """
    have = set(RaceSquad.objects.filter(race=race).values_list("team_id", flat=True))
    for team in Team.objects.exclude(pk__in=have):
        try:
            rider_ids, leader_id = auto_pick_squad(team)
        except SquadError as exc:
            logger.warning("no squad for %s in %s: %s", team, race, exc)
            continue
        _write_squad(race, team, rider_ids, leader_id, auto=True)


def simulate_race(race: Race, *, game_time: datetime) -> list[RaceResult]:
    """Run one race through the engine and record it.

    `game_time` is the world's current game time, passed in because
    `racing/` may not import `world/`. It is stored as `Race.finished_at`.

    Assumes the caller has already claimed the race (status RUNNING). Writes
    the log through Django storage, the results in one transaction, and
    flips the race to FINISHED. Idempotent only in the sense that a FINISHED
    race is refused: call it once per claim.
    """
    if race.status == Race.Status.FINISHED:
        raise ValueError(f"{race} is already finished")

    ensure_squads(race)

    members = list(
        RaceSquadRider.objects
        .filter(squad__race=race)
        .select_related("rider", "squad__team")
    )
    if not members:
        raise ValueError("no squads to race")

    db_riders = [m.rider for m in members]
    engine_riders = [
        to_engine_rider(m.rider, role="leader" if m.is_leader else "support")
        for m in members
    ]
    teams = list({m.squad.team.pk: m.squad.team for m in members}.values())

    course = to_engine_course(race)

    # The engine writes the log itself with a raw open(), and it may not
    # learn about Django. So it writes to a temp file and we hand the
    # finished file to storage — see racing/README.md, logs never bypass
    # the storage API.
    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / f"race-{race.pk}.jsonl"
        states = run_race_via_adapter(
            engine_riders, course, str(log_path), race.seed,
            to_team_codes(teams), race.wind_enabled, race.wind_band or None,
        )
        tick_count = sum(1 for _ in log_path.open())
        size = log_path.stat().st_size
        with log_path.open("rb") as fh:
            saved = ContentFile(fh.read(), name=f"race-{race.pk}.jsonl")

    by_pk = {str(r.pk): r for r in db_riders}
    finishers = sorted(
        states,
        key=lambda s: (s.finish_time is None, s.finish_time if s.finish_time is not None else 0),
    )

    with transaction.atomic():
        RaceLog.objects.update_or_create(
            race=race,
            defaults={"file": saved, "tick_count": tick_count, "size_bytes": size},
        )
        results = RaceResult.objects.bulk_create([
            RaceResult(
                race=race, rider=by_pk[s.rider.id], position=i,
                finish_time=float(s.finish_time) if s.finish_time is not None else None,
            )
            for i, s in enumerate(finishers, start=1)
        ])
        race.status = Race.Status.FINISHED
        race.finished_at = game_time
        race.save(update_fields=["status", "finished_at"])
    return results
