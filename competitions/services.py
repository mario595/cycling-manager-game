from __future__ import annotations

from racing.models import Race, RaceResult

from .models import RacePoints
from .scoring import points_for


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
