"""Builds the payload for GET /api/riders/<rider_id>/ — see
specs/rider-detail-view-plan.md for the design decisions this follows.
Kept out of views.py so it is unit-testable without HTTP, and out of
riders/ because it joins riders/, racing/ and schedule/, which only api/
and world/ may all import (AGENTS.md, *Dependency direction*).
"""

from __future__ import annotations

from datetime import datetime

from django.db.models import F, Min

from racing.models import Race, RaceResult, RaceSquadRider
from riders.models import Rider
from schedule.models import SEASON_WEEKS
from schedule.services import current_position


def _team_payload(team) -> dict:
    return {"id": team.pk, "name": team.name, "code": team.code}


def retired_payload(rider: Rider) -> dict | None:
    """{season, week} the rider retired in, or None if active."""
    if rider.retired_at is None:
        return None

    position = current_position(rider.retired_at)
    if position.state == "no_season":
        return {"season": None, "week": None}
    if position.state == "off_season":
        return {"season": position.season.number, "week": None}
    return {"season": position.season.number, "week": position.week.number}


def rider_profile(rider: Rider, *, at: datetime) -> dict:
    races = race_history(rider)
    return {
        "team": _team_payload(rider.team) if rider.team_id else None,
        "current_week": current_week_payload(at),
        "retired": retired_payload(rider),
        "attribute_history": attribute_history(rider),
        "races": races,
        "career": career_totals(races),
    }


def attribute_history(rider: Rider) -> list[dict]:
    """Baseline (week=None) first, then by (season number, week number) —
    never by created_at, which the backfill made meaningless. See D7."""
    snapshots = list(rider.attribute_snapshots.select_related("week__season"))
    snapshots.sort(
        key=lambda s: (0, 0, 0) if s.week_id is None else (1, s.week.season.number, s.week.number)
    )
    return [
        {
            "season": None if s.week_id is None else s.week.season.number,
            "week": None if s.week_id is None else s.week.number,
            "climb": s.climb,
            "sprint": s.sprint,
            "flat": s.flat,
            "resistance": s.resistance,
            "positioning": s.positioning,
        }
        for s in snapshots
    ]


def race_history(rider: Rider) -> list[dict]:
    """Newest first. The team is the one the rider raced for, from
    RaceSquadRider — never rider.team, which is the current team and would
    mislabel every past race of a moved rider (D4). Fixed query shape
    whatever the career length: one query for results, one for the
    race-to-team map, one for winner times."""
    results = list(
        RaceResult.objects
        .filter(rider=rider, race__status=Race.Status.FINISHED)
        .select_related("race")
        .order_by(F("race__starts_at").desc(nulls_last=True), "-race_id")
    )
    race_ids = [r.race_id for r in results]

    team_by_race = {
        m.squad.race_id: m.squad.team
        for m in RaceSquadRider.objects
            .filter(rider=rider, squad__race_id__in=race_ids)
            .select_related("squad__team")
    }
    winner_time = dict(
        RaceResult.objects
        .filter(race_id__in=race_ids, finish_time__isnull=False)
        .values("race_id").annotate(t=Min("finish_time"))
        .values_list("race_id", "t")
    )

    rows = []
    for r in results:
        team = team_by_race.get(r.race_id)
        rows.append({
            "race": {"id": r.race_id, "name": r.race.name, "starts_at": r.race.starts_at},
            "team": _team_payload(team) if team is not None else None,
            "position": r.position,
            "finish_time": r.finish_time,
            "winner_time": winner_time.get(r.race_id),
            "finished": r.finish_time is not None,
        })
    return rows


def career_totals(races: list[dict]) -> dict:
    """Computed from the same list the page shows, never a separate
    aggregate query — the squad_value precedent (D6). A DNF counts as a
    start and a DNF, never a podium, even though it carries a position."""
    finished = [r for r in races if r["finished"]]
    return {
        "starts": len(races),
        "wins": sum(1 for r in finished if r["position"] == 1),
        "podiums": sum(1 for r in finished if r["position"] <= 3),
        "top_tens": sum(1 for r in finished if r["position"] <= 10),
        "dnfs": sum(1 for r in races if not r["finished"]),
    }


def current_week_payload(at: datetime) -> dict | None:
    """{season, week} or null — see D7. off_season shows the season's last
    week, since it just ended; no_season is null."""
    position = current_position(at)
    if position.state == "no_season":
        return None
    if position.state == "off_season":
        return {"season": position.season.number, "week": SEASON_WEEKS}
    return {"season": position.season.number, "week": position.week.number}
