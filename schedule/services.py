"""Where the world is in its season. See `schedule/README.md`, *Derived, not
stored*.

`current_position` takes `at` as a required parameter and never defaults it
from the clock: `schedule/` must not import `world/` (`AGENTS.md`'s
dependency direction). Callers (`api/`, `world/`) pass `world.services.now()`
in themselves.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .models import Season, Week


@dataclass(frozen=True)
class Position:
    state: str  # "in_season" | "off_season" | "no_season"
    season: Season | None
    week: Week | None


def current_position(at: datetime) -> Position:
    """Where the world is, derived entirely from `at`. No stored pointer —
    see schedule/README.md: a missed tick must never be able to make the
    game display the wrong week.
    """
    season = Season.objects.filter(starts_at__lte=at, ends_at__gt=at).first()
    if season is not None:
        week = season.weeks.filter(starts_at__lte=at, ends_at__gt=at).first()
        return Position(state="in_season", season=season, week=week)

    finished = Season.objects.filter(ends_at__lte=at).order_by("-ends_at").first()
    if finished is not None:
        return Position(state="off_season", season=finished, week=None)

    return Position(state="no_season", season=None, week=None)
