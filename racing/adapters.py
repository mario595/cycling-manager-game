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

from race_engine.models import Course, Rider as EngineRider, RiderAttributes, Segment
from riders.models import ENGINE_ATTRIBUTES

if TYPE_CHECKING:
    from race_engine.models import RiderState
    from riders.models import Rider as DBRider
    from teams.models import Team

    from .models import Race


def to_engine_rider(rider: DBRider, *, role: str | None = None) -> EngineRider:
    """Convert a persisted rider into the dataclass the engine simulates.

    The engine identifies riders by string id; we use the primary key so that
    results coming back out of the engine can be mapped to rows again.

    `role` overrides the rider's own `Rider.role` — the squad selection
    feature (#37) decides who leads *per race*, via `RaceSquadRider.is_leader`,
    so the engine's per-race role no longer comes from the rider row.
    Defaults to `rider.role` so existing callers (and their tests) are
    unaffected.
    """
    attributes = RiderAttributes(
        **{name: getattr(rider, name) for name in ENGINE_ATTRIBUTES}
    )
    return EngineRider(
        id=str(rider.pk),
        name=rider.name,
        attributes=attributes,
        # A rider with no team races as their own one-person team, which is
        # exactly what the engine does when team_id is None.
        team_id=str(rider.team_id) if rider.team_id else None,
        role=role if role is not None else rider.role,
    )


def to_engine_course(race: Race) -> Course:
    """Build the engine's Course from a Race's stored segment JSON."""
    return Course(
        segments=[
            Segment(length=float(s["length"]), gradient=float(s["gradient"]))
            for s in race.course
        ]
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
) -> list[RiderState]:
    """Call the engine's `run_race`. Exists so `racing/services.py` can run a
    race without importing `race_engine` — see this file's module docstring.
    """
    from race_engine.models import run_race

    return run_race(
        riders, course, log_path=log_path, seed=seed, verbose=False,
        team_codes=team_codes, wind=wind, wind_band=wind_band,
    )
