from __future__ import annotations

import json
import re
from typing import Any

from race_engine.models import Course, Rider, RiderAttributes, Segment


class ConfigError(ValueError):
    """Raised when a race config file is malformed or fails validation."""


_TEAM_CODE_RE = re.compile(r"^[A-Z]{3}$")


def _require(obj: Any, key: str, path: str) -> Any:
    if not isinstance(obj, dict):
        raise ConfigError(f"{path} must be an object")
    if key not in obj:
        raise ConfigError(f"missing required field '{key}' at {path}")
    return obj[key]


def _parse_attributes(raw: Any, path: str) -> RiderAttributes:
    climb = _require(raw, "climb", path)
    sprint = _require(raw, "sprint", path)
    flat = _require(raw, "flat", path)
    resistance = _require(raw, "resistance", path)
    positioning = _require(raw, "positioning", path)
    try:
        return RiderAttributes(
            climb=int(climb),
            sprint=int(sprint),
            flat=int(flat),
            resistance=int(resistance),
            positioning=int(positioning),
        )
    except ValueError as exc:
        raise ConfigError(f"{path}: {exc}") from exc


_VALID_ROLES = {"leader", "support"}


def _parse_rider(raw: Any, default_index: int) -> Rider:
    path = f"race.riders[{default_index}]"
    rid = _require(raw, "id", path)
    name = _require(raw, "name", path)
    attrs = _parse_attributes(_require(raw, "attributes", path), f"{path}.attributes")

    team_id = raw.get("team")
    team_id = str(team_id) if team_id is not None else None

    role = raw.get("role", "leader")
    if role not in _VALID_ROLES:
        raise ConfigError(f"{path}.role must be one of {sorted(_VALID_ROLES)}, got {role!r}")

    return Rider(id=str(rid), name=str(name), attributes=attrs, team_id=team_id, role=role)


def _parse_course(raw: Any) -> Course:
    segments_raw = _require(raw, "course", "race")
    if not isinstance(segments_raw, list) or not segments_raw:
        raise ConfigError("race.course must be a non-empty list of segments")

    segments: list[Segment] = []
    for i, seg in enumerate(segments_raw):
        path = f"race.course[{i}]"
        length = _require(seg, "length", path)
        gradient = _require(seg, "gradient", path)
        try:
            segments.append(
                Segment(length=float(length), gradient=float(gradient))
            )
        except (TypeError, ValueError) as exc:
            raise ConfigError(f"{path}: length/gradient must be numbers") from exc
        if segments[-1].length <= 0:
            raise ConfigError(f"{path}.length must be positive")

    return Course(segments=segments)


def _parse_teams(raw: Any) -> dict[str, str]:
    """Parse the optional `race.teams` map: team id -> 3-letter uppercase code.

    This is the TV-style team abbreviation (a UCI team code, e.g. "UAD") —
    display metadata, not something the simulation reads. Absent entirely is
    fine (older configs, or hand-built races with no teams); a team present
    in `race.teams` must have a valid, unique code.
    """
    teams_raw = raw.get("teams")
    if teams_raw is None:
        return {}
    if not isinstance(teams_raw, dict):
        raise ConfigError("race.teams must be an object mapping team id to {\"code\": ...}")

    codes: dict[str, str] = {}
    for team_id, team_obj in teams_raw.items():
        path = f"race.teams.{team_id}"
        code = _require(team_obj, "code", path)
        code = str(code)
        if not _TEAM_CODE_RE.match(code):
            raise ConfigError(f"{path}.code must be exactly 3 uppercase letters, got {code!r}")
        codes[str(team_id)] = code

    seen_codes: dict[str, str] = {}
    for team_id, code in codes.items():
        if code in seen_codes:
            raise ConfigError(
                f"race.teams: code {code!r} used by both {seen_codes[code]!r} and {team_id!r}; "
                "team codes must be unique"
            )
        seen_codes[code] = team_id

    return codes


def load_config(path: str) -> dict[str, Any]:
    """Read and validate a race config file, returning the raw parsed dict."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except OSError as exc:
        raise ConfigError(f"cannot read config file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigError(f"invalid JSON in {path}: {exc}") from exc

    race = _require(raw, "race", "root")
    if not isinstance(race, dict):
        raise ConfigError("'race' must be an object")

    riders_raw = _require(race, "riders", "race")
    if not isinstance(riders_raw, list) or not riders_raw:
        raise ConfigError("race.riders must be a non-empty list")

    riders = [_parse_rider(r, i) for i, r in enumerate(riders_raw)]
    course = _parse_course(race)

    # Require unique rider ids so results/logs map unambiguously to riders.
    ids = [r.id for r in riders]
    if len(set(ids)) != len(ids):
        raise ConfigError("race.riders contains duplicate ids")

    _validate_team_leaders(riders)
    team_codes = _parse_teams(race)

    return {
        "riders": riders,
        "course": course,
        "name": race.get("name"),
        "team_codes": team_codes,
    }


def _validate_team_leaders(riders: list[Rider]) -> None:
    """Exactly one leader per team — zero or two+ is a config error.

    Silent acceptance here would produce races that are confusing to debug:
    a team with no leader has nobody to protect, and a team with two has an
    undefined "the" leader for role-scaled tactics.
    """
    leaders_by_team: dict[str, list[str]] = {}
    for r in riders:
        if r.role == "leader":
            leaders_by_team.setdefault(r.team_id, []).append(r.id)

    for team_id, leader_ids in leaders_by_team.items():
        if len(leader_ids) > 1:
            raise ConfigError(
                f"team {team_id!r} has {len(leader_ids)} leaders {leader_ids}; "
                "exactly one leader is required per team"
            )

    all_teams = {r.team_id for r in riders}
    teams_without_leader = sorted(all_teams - leaders_by_team.keys())
    if teams_without_leader:
        raise ConfigError(
            f"team(s) {teams_without_leader} have no leader; "
            "exactly one leader is required per team"
        )


def build_race(config_path: str) -> tuple[list[Rider], Course]:
    """Build the riders and course objects from a race config file.

    Returns a (riders, course) pair suitable for ``race_engine.run_race``.
    """
    cfg = load_config(config_path)
    return cfg["riders"], cfg["course"]