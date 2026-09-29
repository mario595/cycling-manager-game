from __future__ import annotations

from django.db.models import Sum
from racing.models import Race, RaceResult, StageRace
from racing.services import general_classification
from schedule.models import Season, Week

from .models import RacePoints
from .scoring import (
    POINTS_BY_POSITION,
    gc_points_for,
    gc_prize_for,
    points_for,
    prize_for,
    stage_points_for,
    stage_prize_for,
)


def score_race(race: Race) -> list[RacePoints]:
    """Award points for one finished race, by each team's best classified
    finisher. Idempotent: a race already scored returns its existing rows.

    A stage scores from the reduced STAGE_POINTS_BY_POSITION table rather
    than the one-day POINTS_BY_POSITION table — see specs/stage-races.md,
    Decisions taken. The existing-rows check filters kind=RACE: the final
    stage of a completed tour also carries a GC row (see
    score_general_classification), which must not look like "already
    scored" for its own stage points.

    Raises ValueError if the race is not FINISHED.
    """
    if race.status != Race.Status.FINISHED:
        raise ValueError(f"{race} is not finished; nothing to score")

    existing = list(RacePoints.objects.filter(race=race, kind=RacePoints.Kind.RACE))
    if existing:
        return existing

    points_for_position = stage_points_for if race.stage_race_id else points_for

    # finish_time__isnull=False is the whole of D3 (see
    # specs/race-points-and-standings-plan.md): simulate_race numbers every
    # rider including those who never finished, so an unfiltered
    # min(position) would score a team for abandoning.
    best_by_team: dict[int, int] = {}
    rows = (
        RaceResult.objects
        .filter(race=race, finish_time__isnull=False)
        .values_list("rider__team_id", "position")
    )
    for team_id, position in rows:
        if team_id is None:
            continue
        if team_id not in best_by_team or position < best_by_team[team_id]:
            best_by_team[team_id] = position

    to_create = [
        RacePoints(race=race, team_id=team_id, position=position,
                   points=points_for_position(position), kind=RacePoints.Kind.RACE)
        for team_id, position in best_by_team.items()
        if points_for_position(position) > 0
    ]
    return RacePoints.objects.bulk_create(to_create, ignore_conflicts=True)


def prizes_by_team(race: Race) -> dict[int, list[tuple[int, int]]]:
    """Every placed rider's prize for one finished race, keyed by team.

    {team_id: [(position, amount), ...]} — a team with two riders in the
    top 10 gets two entries in its list, unlike points which credit only
    the best finisher. Read-only: writes nothing, touches no ledger.
    economy/ cannot compute this itself (it may not import racing/ or
    competitions/), so world/ calls this and passes the result into
    economy.services.pay_race_prizes — the same shape points_by_team/
    apply_weekly_fanbase already use for the identical constraint
    (economy/README.md, *Why `economy/` does not query `RacePoints`*).

    A stage pays from the reduced STAGE_PRIZE_BY_POSITION table rather than
    the one-day PRIZE_BY_POSITION table — see specs/stage-races.md,
    Decisions taken.

    Raises ValueError if the race is not FINISHED.
    """
    if race.status != Race.Status.FINISHED:
        raise ValueError(f"{race} is not finished; nothing to pay")

    prize_for_position = stage_prize_for if race.stage_race_id else prize_for

    rows = (
        RaceResult.objects
        .filter(race=race, finish_time__isnull=False)     # non-finishers never pay
        .values_list("rider__team_id", "position")
        .order_by("position")
    )

    by_team: dict[int, list[tuple[int, int]]] = {}
    for team_id, position in rows:
        if team_id is None:                # team-less rider: spec item 5
            continue
        amount = prize_for_position(position)
        if amount <= 0:
            continue
        by_team.setdefault(team_id, []).append((position, amount))
    return by_team


def score_general_classification(stage_race: StageRace) -> list[RacePoints]:
    """Award GC points on the final stage, once, when the whole stage race
    has completed — D11, specs/stage-races.md, In scope 8.

    Idempotent the same way score_race is: existing kind=GC rows for the
    final stage are returned unchanged rather than re-created. Each team's
    best-placed GC rider scores, from GC_POINTS_BY_POSITION — the GC
    counterpart of score_race's best-classified-finisher rule.

    Raises ValueError unless the stage race is complete.
    """
    if not stage_race.is_complete():
        raise ValueError(f"{stage_race} is not complete; nothing to score")

    final_stage = stage_race.final_stage()
    existing = list(RacePoints.objects.filter(race=final_stage, kind=RacePoints.Kind.GC))
    if existing:
        return existing

    to_create = []
    seen_teams: set[int] = set()
    for position, entry in enumerate(general_classification(stage_race), start=1):
        if entry.team_id is None or entry.team_id in seen_teams:
            continue
        points = gc_points_for(position)
        if points <= 0:
            continue
        seen_teams.add(entry.team_id)
        to_create.append(RacePoints(
            race=final_stage, team_id=entry.team_id, position=position,
            points=points, kind=RacePoints.Kind.GC,
        ))
    return RacePoints.objects.bulk_create(to_create, ignore_conflicts=True)


def gc_prizes_by_team(stage_race: StageRace) -> dict[int, list[tuple[int, int]]]:
    """Every placed GC rider's prize, keyed by team — the GC counterpart of
    prizes_by_team. Unlike GC points (best rider per team only), every
    placed GC rider's team is paid, matching prizes_by_team's rule for a
    one-day race. Read-only: writes nothing, touches no ledger — world/
    passes the result into economy.services.pay_gc_prizes.

    Raises ValueError unless the stage race is complete.
    """
    if not stage_race.is_complete():
        raise ValueError(f"{stage_race} is not complete; nothing to pay")

    by_team: dict[int, list[tuple[int, int]]] = {}
    for position, entry in enumerate(general_classification(stage_race), start=1):
        if entry.team_id is None:
            continue
        amount = gc_prize_for(position)
        if amount <= 0:
            continue
        by_team.setdefault(entry.team_id, []).append((position, amount))
    return by_team


def _countback_key(entry: dict) -> tuple:
    """Sort key for standings(): most points first, then most 1st places,
    then most 2nd places, and so on down the scoring positions. Negated
    throughout: Python sorts ascending, and more is better for every
    component here."""
    counts = entry["positions"]
    return (-entry["points"],) + tuple(
        -counts.get(position, 0) for position in sorted(POINTS_BY_POSITION)
    )


def points_by_team(week: Week) -> dict[int, int]:
    """Total race points each team scored in `week`. Teams that scored
    nothing are absent from the mapping — callers treat a missing key as 0.

    Read by world.services.tick() and handed to economy's fanbase
    adjustment: economy/ may not import competitions/ (AGENTS.md), so the
    caller does the join. Same shape as score_race being called from
    world/ rather than from racing/.
    """
    rows = (
        RacePoints.objects
        .filter(race__week=week)
        .values("team_id")
        .annotate(total=Sum("points"))
    )
    return {row["team_id"]: row["total"] for row in rows}


def standings(season: Season) -> list[dict]:
    """The season's table: every team, total points, and countback.

    Ordered by total points descending, then by most 1st places, then most
    2nd places, and so on down the scoring positions. A team with no points
    sorts last.

    Each entry: {"team": Team, "points": int, "positions": {pos: count}}.
    """
    rows = (
        RacePoints.objects
        .filter(race__week__season=season)
        .select_related("team")
    )

    by_team: dict[int, dict] = {}
    for row in rows:
        entry = by_team.setdefault(row.team_id, {
            "team": row.team, "points": 0, "positions": {},
        })
        entry["points"] += row.points
        entry["positions"][row.position] = entry["positions"].get(row.position, 0) + 1

    return sorted(by_team.values(), key=_countback_key)
