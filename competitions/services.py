from __future__ import annotations

from collections.abc import Callable

from django.db.models import Sum
from racing.models import MarkerCrossing, Race, RaceMarker, RaceResult
from schedule.models import Season, Week
from teams.models import Team

from .models import MarkerPoints, RacePoints
from .scoring import (
    MOUNTAIN_PLACES,
    POINTS_BY_POSITION,
    SPRINT_PLACES,
    mountain_points_for,
    points_for,
    prize_for,
    sprint_points_for,
)


def score_race(race: Race) -> list[RacePoints]:
    """Award points for one finished race, by each team's best classified
    finisher. Idempotent: a race already scored returns its existing rows.

    Raises ValueError if the race is not FINISHED.
    """
    if race.status != Race.Status.FINISHED:
        raise ValueError(f"{race} is not finished; nothing to score")

    existing = list(RacePoints.objects.filter(race=race))
    if existing:
        return existing

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
                   points=points_for(position))
        for team_id, position in best_by_team.items()
        if points_for(position) > 0
    ]
    return RacePoints.objects.bulk_create(to_create, ignore_conflicts=True)


def _score_markers(
    race: Race,
    kind: str,
    places: int,
    points_for: Callable[[RaceMarker, int], int],
) -> list[MarkerPoints]:
    """Award one kind of marker points for one finished race: per marker of
    `kind`, each team's best-placed rider among the top `places` crossings.
    Idempotent per kind: a kind already scored for this race returns its
    existing rows.

    Raises ValueError if the race is not FINISHED.
    """
    if race.status != Race.Status.FINISHED:
        raise ValueError(f"{race} is not finished; nothing to score")

    # The guard is filtered by kind deliberately. Unfiltered, whichever of
    # sprints and mountains ran second would find the other's rows and score
    # nothing — with no error anywhere to say so.
    existing = list(MarkerPoints.objects.filter(marker__race=race, marker__kind=kind))
    if existing:
        return existing

    to_create = []
    for marker in race.markers.filter(kind=kind):
        # Cut to the top `places` crossings FIRST, then keep each team's
        # best among them — not the reverse. Walking down the crossing order
        # until five distinct teams have scored would let a 6th-place rider
        # score when a teammate already took two of the top five, which is
        # exactly the double-scoring the best-rider rule exists to prevent.
        crossings = (
            MarkerCrossing.objects
            .filter(marker=marker, position__lte=places)
            .order_by("position")
            .values_list("rider_id", "rider__team_id", "position")
        )
        best: dict[int, tuple[int, int]] = {}
        for rider_id, team_id, position in crossings:
            if team_id is None or team_id in best:
                continue
            best[team_id] = (rider_id, position)
        to_create += [
            MarkerPoints(marker=marker, team_id=team_id, rider_id=rider_id,
                         position=position, points=points_for(marker, position))
            for team_id, (rider_id, position) in best.items()
        ]
    return MarkerPoints.objects.bulk_create(to_create, ignore_conflicts=True)


def score_sprints(race: Race) -> list[MarkerPoints]:
    """Sprint points for one finished race. See _score_markers."""
    return _score_markers(race, RaceMarker.Kind.SPRINT, SPRINT_PLACES,
                          lambda m, p: sprint_points_for(m.weight, p))


def score_mountains(race: Race) -> list[MarkerPoints]:
    """Mountain points for one finished race. See _score_markers."""
    return _score_markers(race, RaceMarker.Kind.MOUNTAIN, MOUNTAIN_PLACES,
                          lambda m, p: mountain_points_for(m.category, p))


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

    Raises ValueError if the race is not FINISHED.
    """
    if race.status != Race.Status.FINISHED:
        raise ValueError(f"{race} is not finished; nothing to pay")

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
        amount = prize_for(position)
        if amount <= 0:
            continue
        by_team.setdefault(team_id, []).append((position, amount))
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
    """Total points each team scored in `week` — finish points plus sprint
    and mountain marker points. Teams that scored nothing are absent from the
    mapping — callers treat a missing key as 0.

    Read by world.services.tick() and handed to economy's fanbase
    adjustment: economy/ may not import competitions/ (AGENTS.md), so the
    caller does the join. Same shape as score_race being called from
    world/ rather than from racing/.
    """
    totals: dict[int, int] = {}
    finish_rows = (
        RacePoints.objects
        .filter(race__week=week)
        .values("team_id")
        .annotate(total=Sum("points"))
    )
    for row in finish_rows:
        totals[row["team_id"]] = totals.get(row["team_id"], 0) + row["total"]

    marker_rows = (
        MarkerPoints.objects
        .filter(marker__race__week=week)
        .values("team_id")
        .annotate(total=Sum("points"))
    )
    for row in marker_rows:
        totals[row["team_id"]] = totals.get(row["team_id"], 0) + row["total"]

    return totals


def standings(season: Season) -> list[dict]:
    """The season's table: every team, total points, and countback.

    Ordered by total points descending, then by most 1st places, then most
    2nd places, and so on down the scoring positions. A team with no points
    sorts last. Countback counts finish positions only — a sprint or climb
    win is not a "1st place" for tie-breaking, so a team that only ever
    scored via markers sorts last among equal point totals.

    Each entry: {"team": Team, "points": int, "sprint_points": int,
    "mountain_points": int, "positions": {pos: count}}. `points` is the
    combined total; the countback key ignores sprint_points and
    mountain_points entirely.
    """
    rows = (
        RacePoints.objects
        .filter(race__week__season=season)
        .select_related("team")
    )

    by_team: dict[int, dict] = {}
    for row in rows:
        entry = by_team.setdefault(row.team_id, {
            "team": row.team, "points": 0, "sprint_points": 0,
            "mountain_points": 0, "positions": {},
        })
        entry["points"] += row.points
        entry["positions"][row.position] = entry["positions"].get(row.position, 0) + 1

    # Grouped by kind so a climb never lands in a sprint's column, and so a
    # team that scored only on climbs still gets an entry.
    marker_rows = list(
        MarkerPoints.objects
        .filter(marker__race__week__season=season)
        .values("team_id", "marker__kind")
        .annotate(total=Sum("points"))
    )
    missing_team_ids = [
        row["team_id"] for row in marker_rows if row["team_id"] not in by_team
    ]
    teams_by_id = Team.objects.in_bulk(missing_team_ids)
    for row in marker_rows:
        entry = by_team.setdefault(row["team_id"], {
            "team": teams_by_id.get(row["team_id"]), "points": 0,
            "sprint_points": 0, "mountain_points": 0, "positions": {},
        })
        entry["points"] += row["total"]
        component = (
            "sprint_points" if row["marker__kind"] == RaceMarker.Kind.SPRINT
            else "mountain_points"
        )
        entry[component] += row["total"]

    return sorted(by_team.values(), key=_countback_key)
