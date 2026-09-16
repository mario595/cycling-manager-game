from __future__ import annotations

from racing.models import Race, RaceResult
from schedule.models import Season

from .models import RacePoints
from .scoring import POINTS_BY_POSITION, points_for


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


def _countback_key(entry: dict) -> tuple:
    """Sort key for standings(): most points first, then most 1st places,
    then most 2nd places, and so on down the scoring positions. Negated
    throughout: Python sorts ascending, and more is better for every
    component here."""
    counts = entry["positions"]
    return (-entry["points"],) + tuple(
        -counts.get(position, 0) for position in sorted(POINTS_BY_POSITION)
    )


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
