"""Translation between Django models and `race_engine` dataclasses.

This module is the **only** place in the project allowed to import from
`race_engine`. Everything else goes through here. The point is to keep the
engine a pure-Python, database-free library: it stays fast to run in bulk,
testable without a database, and free to change its internals without a
migration.

Direction of dependency is one-way and must stay that way:

    racing.adapters  ->  race_engine        (fine)
    race_engine      ->  django / racing    (never)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from race_engine.models import (
    Course,
    Marker,
    MarkerKind,
    Rider as EngineRider,
    RiderAttributes,
    Segment,
)
from riders.models import ENGINE_ATTRIBUTES

if TYPE_CHECKING:
    from race_engine.models import RiderState
    from riders.models import Rider as DBRider
    from teams.models import Team

    from .models import Race, RaceMarker


def _scaled(value: int, scale: float) -> int:
    """Apply a freshness scale, rounding and clamping into [1, 100].

    The engine validates its own attribute range, so an unclamped value
    would raise mid-race.
    """
    return max(1, min(100, round(value * scale)))


def to_engine_rider(rider: DBRider, *, role: str, freshness_scale: float = 1.0) -> EngineRider:
    """Convert a persisted rider into the dataclass the engine simulates.

    The engine identifies riders by string id; we use the primary key so that
    results coming back out of the engine can be mapped to rows again.

    A rider has no role of their own — leadership is a per-race property held
    by `RaceSquadRider.is_leader`, decided when a squad is picked. `role` is
    therefore required, not defaulted: the caller must derive it from the
    squad for this race, and a caller that forgets fails loudly here rather
    than sending an unintended role into the engine.

    `freshness_scale` defaults to 1.0 so existing callers and tests that do
    not care about fatigue keep working unchanged. `simulate_race` passes a
    real value computed from `rider.freshness` via
    `riders.services.freshness_multiplier`.
    """
    attributes = RiderAttributes(**{
        name: _scaled(getattr(rider, name), freshness_scale)
        for name in ENGINE_ATTRIBUTES
    })
    return EngineRider(
        id=str(rider.pk),
        name=rider.name,
        attributes=attributes,
        # A rider with no team races as their own one-person team, which is
        # exactly what the engine does when team_id is None.
        team_id=str(rider.team_id) if rider.team_id else None,
        role=role,
    )


def to_engine_course(race: Race, markers: list[RaceMarker]) -> Course:
    """Build the engine's Course from a Race's stored segment JSON.

    `markers` is **required**, not defaulted — D9: the caller fetches the
    marker rows once and passes the same list both here and to the crossing
    writer, so the engine's marker index always refers to the same
    `RaceMarker` row. Each row maps in the given order, which is the
    `("distance", "pk")` Meta ordering.
    """
    return Course(
        segments=[
            Segment(length=float(s["length"]), gradient=float(s["gradient"]))
            for s in race.course
        ],
        markers=[
            Marker(kind=MarkerKind(m.kind), distance=m.distance, name=m.name)
            for m in markers
        ],
    )


def to_team_codes(teams: list[Team]) -> dict[str, dict[str, str]]:
    """Build the team-code/colour map the race logger writes into the log.

    Shape matches what `race_player` expects; see `race_player/README.md`.
    """
    return {
        str(team.pk): {
            "code": team.code,
            "name": team.name,
            "colour": team.primary_colour,
            "secondary": team.secondary_colour,
        }
        for team in teams
    }


def run_race_via_adapter(
    riders: list[EngineRider],
    course: Course,
    log_path: str,
    seed: int | None,
    team_codes: dict[str, dict[str, str]],
    wind: bool,
    wind_band: str | None,
) -> tuple[list[RiderState], int, int]:
    """Call the engine's `run_race`. Exists so `racing/services.py` can run a
    race without importing `race_engine` — see this file's module docstring.

    Returns the engine's ``(states, sample_count, sample_interval)`` untouched:
    the adapter is still the only import of the engine, and the caller records
    the log metadata straight from it.
    """
    from race_engine.models import run_race

    return run_race(
        riders, course, log_path=log_path, seed=seed, verbose=False,
        team_codes=team_codes, wind=wind, wind_band=wind_band,
    )
