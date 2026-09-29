"""Simulating a race and recording its result.

`racing/` owns simulation; `world/` calls it — never the reverse (`AGENTS.md`
forbids `racing/` importing `world/`). `game_time` is therefore a parameter,
not read from the clock here.
"""

from __future__ import annotations

import logging
import tempfile
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import F

from riders.models import ENGINE_ATTRIBUTES, Rider
from riders.services import RACE_FRESHNESS_COST, STAGE_FRESHNESS_COST, apply_race_cost, freshness_multiplier
from teams.models import Team

from .adapters import run_race_via_adapter, to_engine_course, to_engine_rider, to_team_codes
from .models import (
    SQUAD_SIZE,
    Race,
    RaceLog,
    RaceMarker,
    RaceResult,
    RaceSquad,
    RaceSquadRider,
    MarkerCrossing,
)

logger = logging.getLogger(__name__)


class SquadError(ValueError):
    """An invalid squad: wrong size, a rider from another team, or not
    exactly one leader. Raised by set_squad and turned into a 400 by the
    API."""


#: Distance-weighted mean gradient (%) at or above which a course trains climb.
CLIMB_GRADIENT_THRESHOLD = 2.0
#: Courses at or under this length (m) with no real climbing train sprint.
SPRINT_MAX_DISTANCE = 120_000
#: Courses at or over this length (m) train resistance.
RESISTANCE_MIN_DISTANCE = 200_000

#: Finishers separated by no more than this many seconds from the rider
#: ahead of them share a group time (specs/stage-races.md, In scope 6).
#: Finish times are whole seconds (the engine ticks at 1s), so this is the
#: smallest threshold that groups more than riders crossing the same tick.
GROUP_GAP_SECONDS = 1.0


def group_times(finish_times: list[float]) -> list[float]:
    """Each finisher's group time: the time of the first rider of their
    group. A new group starts when the gap to the PREVIOUS finisher exceeds
    GROUP_GAP_SECONDS — chained, so a bunch strung out over several
    consecutive small gaps is still one group. `finish_times` must be
    sorted ascending and contain only finishers.
    """
    out: list[float] = []
    head = None
    for i, t in enumerate(finish_times):
        if i == 0 or t - finish_times[i - 1] > GROUP_GAP_SECONDS:
            head = t
        out.append(head)
    return out


def course_training_attribute(course: list[dict]) -> str:
    """Which rider attribute racing this course rewards.

    Pure function over the stored Race.course JSON — deliberately not a
    read of race_engine.models.Terrain, which only racing/adapters.py may
    import (AGENTS.md). Never returns "positioning": no course shape
    distinctly rewards draft skill. See specs/weekly-training-focus-plan.md,
    Design decision 4.
    """
    total_length = sum(s["length"] for s in course)
    weighted_gradient = (
        sum(s["length"] * s["gradient"] for s in course) / total_length
    ) if total_length else 0.0

    if total_length == 0:
        return "flat"
    if weighted_gradient >= CLIMB_GRADIENT_THRESHOLD:
        return "climb"
    if total_length >= RESISTANCE_MIN_DISTANCE:
        return "resistance"
    if total_length <= SPRINT_MAX_DISTANCE:
        return "sprint"
    return "flat"


def riders_who_raced(week) -> dict[int, list[str]]:
    """{rider_id: [training attribute per race they finished]} for one week.

    The *training* reader — see `riders_who_started` for the fatigue one.
    One query over RaceResult joined to Race, not one query per race. A
    rider who raced twice in a week appears with two entries and is
    trained for both. Non-finishers are excluded — `RaceResult.position`
    is assigned to everyone, so only `finish_time` says a rider actually
    finished; a rider cut by the time limit started but didn't complete
    the course, so there's nothing to have learned from it. See
    racing/README.md.
    """
    results = (
        RaceResult.objects.filter(race__week=week, finish_time__isnull=False)
        .select_related("race")
    )
    raced: dict[int, list[str]] = {}
    for result in results:
        raced.setdefault(result.rider_id, []).append(
            course_training_attribute(result.race.course)
        )
    return raced


def riders_who_started(week) -> set[int]:
    """Every rider with a RaceResult in `week`'s races, finisher or not.

    The *fatigue* reader — see `riders_who_raced` for the training one.
    Missing a race costs a rider's legs the same as racing it, so weekly
    recovery excludes every starter, not just finishers (see
    riders/README.md, Freshness).
    """
    return set(
        RaceResult.objects.filter(race__week=week).values_list("rider_id", flat=True)
    )


def auto_pick_squad(team: Team) -> tuple[list[int], int]:
    """Four rider ids and the leader's id, chosen naively.

    By total engine attributes weighted by freshness
    (riders.services.freshness_multiplier), descending, then by pk
    ascending — the pk tiebreak is what makes this deterministic and so
    testable. The strongest rider leads. Deliberately course-blind: see
    specs/squad-selection.md, Out of scope, and #45.

    The weighting is a light preference, not an optimiser — the same
    multiplier the engine penalty uses, so an unmanaged team does not
    mechanically run its best four into the ground. A much stronger tired
    rider still outranks a weak fresh one.

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
            -sum(getattr(r, name) for name in ENGINE_ATTRIBUTES)
            * freshness_multiplier(r.freshness),
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


def create_race(*, markers: Iterable[dict] = (), **fields) -> Race:
    """Create a race and its markers in one transaction.

    `markers` entries are `{"kind", "name", "distance"}` dicts, as the
    season loader produces them. Each `save()` runs `RaceMarker.clean()`, so
    an invalid marker fails the whole creation. `schedule/`'s loader injects
    this in place of `Race.objects.create` — D10: markers are authored in the
    same declaration as the race, and the loader still imports nothing from
    `racing/`.
    """
    with transaction.atomic():
        race = Race.objects.create(**fields)
        for marker in markers:
            RaceMarker.objects.create(
                race=race,
                kind=marker["kind"],
                name=marker["name"],
                distance=marker["distance"],
            )
    return race


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


def _effective_leader_ids(members: list[RaceSquadRider]) -> set[int]:
    """Which riders race as leader, after simulate_race has dropped any
    squad member whose rider has left the team.

    Normally this is just whoever the manager marked `is_leader`. But if
    that rider was the one dropped, their team still races (the remaining
    members) with no leader among them — and the engine requires exactly
    one leader per team present (`race_engine.models.validate_team_leaders`).
    The lowest-pk remaining member of that team is promoted for this race
    only; the squad's own stored `is_leader` is untouched, since this is a
    simulation-time workaround, not a correction to what the manager
    picked.
    """
    by_team: dict[int, list[RaceSquadRider]] = {}
    for m in members:
        by_team.setdefault(m.squad.team_id, []).append(m)

    leader_ids: set[int] = set()
    for team_members in by_team.values():
        leader = next((m for m in team_members if m.is_leader), team_members[0])
        leader_ids.add(leader.rider_id)
    return leader_ids


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

    # A squad member whose rider has since left the team it was picked
    # for — sold in an auction, released to the free agent pool, whatever
    # moved them — is dropped rather than raced: the squad was picked for
    # a roster that no longer holds them, and racing them here would let
    # the engine and score_race/prizes_by_team (which both read the
    # rider's CURRENT team_id, not the squad's) credit the result to
    # whichever team they belong to now, not the team that actually
    # fielded them. The team that picked them simply races a man short —
    # the same outcome as if they had never had that rider at all.
    members = list(
        RaceSquadRider.objects
        .filter(squad__race=race, rider__team_id=F("squad__team_id"))
        .select_related("rider", "squad__team")
        .order_by("rider__pk")
    )
    if not members:
        raise ValueError("no squads to race")

    leader_ids = _effective_leader_ids(members)
    db_riders = [m.rider for m in members]
    engine_riders = [
        to_engine_rider(
            m.rider,
            role="leader" if m.rider_id in leader_ids else "support",
            freshness_scale=freshness_multiplier(m.rider.freshness),
        )
        for m in members
    ]
    teams = list({m.squad.team.pk: m.squad.team for m in members}.values())

    # D9: fetch once, in index order — the positions below and the crossings
    # writer both use this same list, so the engine's marker index always
    # refers to the same RaceMarker row.
    markers = list(race.markers.order_by("distance", "pk"))
    course = to_engine_course(race, markers)

    # The engine writes the log itself with a raw open(), and it may not
    # learn about Django. So it writes to a temp file and we hand the
    # finished file to storage — see racing/README.md, logs never bypass
    # the storage API. The log is brotli-compressed (a short one-word
    # payload), so the size recorded is the compressed size, and the sample
    # count comes back from the engine rather than by counting lines of a
    # binary stream.
    with tempfile.TemporaryDirectory() as tmp:
        log_path = Path(tmp) / f"race-{race.pk}.jsonl.br"
        states, sample_count, tick_interval = run_race_via_adapter(
            engine_riders, course, str(log_path), race.seed,
            to_team_codes(teams), race.wind_enabled, race.wind_band or None,
        )
        size = log_path.stat().st_size
        with log_path.open("rb") as fh:
            saved = ContentFile(fh.read(), name=f"race-{race.pk}.jsonl.br")

    by_pk = {str(r.pk): r for r in db_riders}
    # Finishers first by time, then non-finishers furthest-travelled first —
    # the engine now produces real non-finishers (cut by the time limit),
    # not just abandons, so this must order them rather than leave them in
    # whatever order they happen to appear (race_engine/README.md, get_results).
    ordered = sorted(
        states,
        key=lambda s: (s.finish_time is None, s.finish_time or 0, -s.position),
    )

    with transaction.atomic():
        RaceLog.objects.update_or_create(
            race=race,
            defaults={
                "file": saved,
                "sample_count": sample_count,
                "tick_interval": tick_interval,
                "size_bytes": size,
            },
        )
        # group_time (D5, specs/stage-races.md In scope 6): computed only
        # over the finishers, who are already the ascending-time prefix of
        # `ordered`. Written for every race, one-day included — only a
        # stage race's general classification ever reads it.
        finishers = [s for s in ordered if s.finish_time is not None]
        groups = group_times([float(s.finish_time) for s in finishers])
        group_time_by_rider = {
            s.rider.id: g for s, g in zip(finishers, groups)
        }
        results = RaceResult.objects.bulk_create([
            RaceResult(
                race=race, rider=by_pk[s.rider.id], position=i,
                finish_time=float(s.finish_time) if s.finish_time is not None else None,
                group_time=group_time_by_rider.get(s.rider.id),
            )
            for i, s in enumerate(ordered, start=1)
        ])
        # Every starter pays, finisher or cut by the time limit — missing a
        # race takes just as much out of a rider's legs as running it does
        # (broom-wagon-time-cut spec, In scope 5). Written here, in the
        # results transaction, so "started" and "paid for it" are atomic —
        # see the plan's Design decision 7. A stage costs less than a full
        # one-day race (specs/stage-races.md, Decisions taken).
        apply_race_cost(
            [by_pk[s.rider.id].pk for s in states],
            cost=STAGE_FRESHNESS_COST if race.stage_race_id else RACE_FRESHNESS_COST,
        )
        # Marker crossings join the same transaction, after the results they
        # are written against. A crossing row is a fact of what happened,
        # never amended later, so it is written once here. Ordering: D5 makes
        # a finish-line marker's order the results' order; D4 gives an
        # in-course marker the stable interpolated crossing time, ordered the
        # same way the audit sorts is, with ties left to state order.
        course_length = sum(s["length"] for s in race.course)
        crossings = []
        for idx, marker in enumerate(markers):
            if marker.distance >= course_length:  # D5: finish line
                crossers = [
                    (s, float(s.finish_time))
                    for s in ordered
                    if s.finish_time is not None
                ]
            else:  # D4: interpolated time, stable
                crossers = sorted(
                    (
                        (s, s.marker_times[idx])
                        for s in states
                        if idx in s.marker_times
                    ),
                    key=lambda pair: pair[1],
                )
            crossings += [
                MarkerCrossing(
                    marker=marker, rider=by_pk[s.rider.id], position=p, crossed_at=t
                )
                for p, (s, t) in enumerate(crossers, start=1)
            ]
        MarkerCrossing.objects.bulk_create(crossings)
        race.status = Race.Status.FINISHED
        race.finished_at = game_time
        race.save(update_fields=["status", "finished_at"])
    return results
