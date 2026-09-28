"""Parsing a season declaration file: the season itself, and (once #7 lands
fully) the races within it.

`parse_season_file` does all validation that does not need the database —
shape, types, ranges, the course, the wind band, and the one-race-per-day
check. It imports nothing from `racing/`, `world/` or `race_engine/`, which
is what lets its tests run with no database. See `schedule/README.md`, *Why
the course is validated twice*.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone as dt_timezone
from typing import Any, Callable

from django.utils import timezone
from django.utils.dateparse import parse_datetime

from .models import SEASON_WEEKS, Season

DAY_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}

_VALID_WIND_BANDS = {"calm", "light", "moderate", "strong"}

_KNOWN_KEYS = {"number", "starts_at", "races"}
_KNOWN_RACE_KEYS = {"week", "day", "time", "name", "course", "wind", "seed", "markers"}
_KNOWN_MARKER_KEYS = {"kind", "name", "distance", "weight"}

#: Duplicated from racing.RaceMarker.Weight — this module may not import
#: racing/. racing/tests.py checks the two stay in sync.
MARKER_WEIGHTS = ("minor", "standard", "major")


class SeasonFileError(ValueError):
    """A season declaration file is malformed. Message is admin-facing."""


@dataclass(frozen=True)
class RaceDeclaration:
    week: int
    day: str
    time: time
    name: str
    course: list[dict[str, float]]
    wind_enabled: bool
    wind_band: str | None
    seed: int | None
    markers: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class SeasonDeclaration:
    number: int
    starts_at: datetime
    races: list[RaceDeclaration] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def parse_season_file(data: dict) -> SeasonDeclaration:
    """Parse and validate a season declaration file's contents.

    Raises `SeasonFileError` naming the problem. Unknown top-level keys are
    collected as warnings rather than rejected — see
    `schedule/README.md`, *Declaring a season*.
    """
    warnings: list[str] = []

    unknown_keys = set(data) - _KNOWN_KEYS
    if unknown_keys:
        warnings.append(f"ignoring unknown key(s): {', '.join(sorted(unknown_keys))}")

    number = data.get("number")
    if not isinstance(number, int) or number < 1:
        raise SeasonFileError("'number' must be an integer >= 1")

    raw_starts_at = data.get("starts_at")
    if not isinstance(raw_starts_at, str):
        raise SeasonFileError("'starts_at' is required and must be an ISO 8601 string")
    starts_at = parse_datetime(raw_starts_at)
    if starts_at is None:
        raise SeasonFileError(f"could not parse 'starts_at': {raw_starts_at!r}")
    if timezone.is_naive(starts_at):
        starts_at = timezone.make_aware(starts_at, dt_timezone.utc)

    starts_at_utc = timezone.localtime(starts_at, dt_timezone.utc)
    if starts_at_utc.weekday() != 0 or starts_at_utc.time() != time(0, 0, 0):
        nearest_monday = starts_at_utc.date() - timedelta(days=starts_at_utc.weekday())
        raise SeasonFileError(
            f"'starts_at' must be a Monday at 00:00:00 UTC; "
            f"got {starts_at_utc.isoformat()}, nearest Monday is {nearest_monday}"
        )

    races_raw = data.get("races", [])
    if not isinstance(races_raw, list):
        raise SeasonFileError("'races' must be a list")

    races: list[RaceDeclaration] = []
    seen: dict[tuple[int, str], str] = {}
    for i, race_raw in enumerate(races_raw):
        path = f"races[{i}]"
        race = _parse_race(race_raw, path, warnings)
        key = (race.week, race.day)
        if key in seen:
            raise SeasonFileError(
                f"two races on week {race.week} {race.day}: "
                f"{seen[key]!r} and {race.name!r}; at most one race per day"
            )
        seen[key] = race.name
        races.append(race)

    return SeasonDeclaration(
        number=number, starts_at=starts_at, races=races, warnings=warnings,
    )


def _parse_race(raw: Any, path: str, warnings: list[str]) -> RaceDeclaration:
    if not isinstance(raw, dict):
        raise SeasonFileError(f"{path} must be an object")

    unknown_keys = set(raw) - _KNOWN_RACE_KEYS
    if unknown_keys:
        warnings.append(f"{path}: ignoring unknown key(s): {', '.join(sorted(unknown_keys))}")

    week = raw.get("week")
    if not isinstance(week, int) or not (1 <= week <= SEASON_WEEKS):
        raise SeasonFileError(f"{path}.week must be an integer from 1 to {SEASON_WEEKS}")

    day = raw.get("day")
    if day not in DAY_INDEX:
        raise SeasonFileError(f"{path}.day must be one of {sorted(DAY_INDEX)}, got {day!r}")

    race_time = _parse_time(raw.get("time"), path, warnings)

    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        raise SeasonFileError(f"{path}.name must be a non-empty string")
    if len(name) > 150:
        raise SeasonFileError(f"{path}.name must be at most 150 characters")

    course = _parse_course(raw.get("course"), f"{path}.course")
    course_length = sum(seg["length"] for seg in course)
    markers = _parse_markers(
        raw.get("markers"), f"{path}.markers", course_length, warnings,
    )
    wind_enabled, wind_band = _parse_wind(raw.get("wind"), path)
    seed = _parse_seed(raw.get("seed"), path)

    return RaceDeclaration(
        week=week, day=day, time=race_time, name=name, course=course,
        wind_enabled=wind_enabled, wind_band=wind_band, seed=seed,
        markers=markers,
    )


def _parse_time(raw: Any, path: str, warnings: list[str]) -> time:
    if not isinstance(raw, str):
        raise SeasonFileError(f"{path}.time must be a string in HH:MM format")
    parts = raw.split(":")
    if len(parts) != 2:
        raise SeasonFileError(f"{path}.time must be in HH:MM format, got {raw!r}")
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        raise SeasonFileError(f"{path}.time must be in HH:MM format, got {raw!r}")
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise SeasonFileError(f"{path}.time is out of range: {raw!r}")
    if minute != 0:
        warnings.append(
            f"{path}.time is {raw!r}: the tick runs hourly, so this race "
            f"starts at the next full hour after {hour:02d}:00"
        )
    return time(hour, minute)


def _parse_course(raw: Any, path: str) -> list[dict[str, float]]:
    if not isinstance(raw, list) or not raw:
        raise SeasonFileError(f"{path} must be a non-empty list of segments")
    segments = []
    for i, seg in enumerate(raw):
        at = f"{path}[{i}]"
        if not isinstance(seg, dict):
            raise SeasonFileError(f"{at} must be an object")
        for key in ("length", "gradient"):
            if key not in seg:
                raise SeasonFileError(f"{at} is missing '{key}'")
        try:
            length, gradient = float(seg["length"]), float(seg["gradient"])
        except (TypeError, ValueError):
            raise SeasonFileError(f"{at}: length and gradient must be numbers")
        if length <= 0:
            raise SeasonFileError(f"{at}.length must be positive")
        segments.append({"length": length, "gradient": gradient})
    return segments


def _parse_markers(
    raw: Any, path: str, course_length: float, warnings: list[str],
) -> list[dict[str, Any]]:
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise SeasonFileError(f"{path} must be a list of markers")
    markers = []
    for i, entry in enumerate(raw):
        at = f"{path}[{i}]"
        if not isinstance(entry, dict):
            raise SeasonFileError(f"{at} must be an object")
        unknown_keys = set(entry) - _KNOWN_MARKER_KEYS
        if unknown_keys:
            warnings.append(
                f"{at}: ignoring unknown key(s): {', '.join(sorted(unknown_keys))}"
            )
        kind = entry.get("kind")
        if kind not in ("sprint", "mountain"):
            raise SeasonFileError(
                f"{at}.kind must be 'sprint' or 'mountain', got {kind!r}"
            )
        name = entry.get("name")
        if not isinstance(name, str) or not name.strip():
            raise SeasonFileError(f"{at}.name must be a non-empty string")
        if len(name) > 100:
            raise SeasonFileError(f"{at}.name must be at most 100 characters")
        try:
            distance = float(entry["distance"])
        except (TypeError, ValueError):
            raise SeasonFileError(f"{at}.distance must be a number")
        if not 0 < distance <= course_length:
            raise SeasonFileError(
                f"{at}.distance must be in (0, {course_length}] meters, got {distance}"
            )
        weight = entry.get("weight")
        if weight is not None and kind == "mountain":
            raise SeasonFileError(f"{at}.weight is only allowed on sprint markers")
        if weight is None:
            weight = "standard"
        elif weight not in MARKER_WEIGHTS:
            raise SeasonFileError(
                f"{at}.weight must be one of {', '.join(MARKER_WEIGHTS)}, got {weight!r}"
            )
        markers.append({"kind": kind, "name": name, "distance": distance, "weight": weight})
    return markers


def _parse_wind(raw: Any, path: str) -> tuple[bool, str | None]:
    if raw is None:
        return True, None
    if not isinstance(raw, dict):
        raise SeasonFileError(f"{path}.wind must be an object")

    band = raw.get("band")
    if band is not None and band not in _VALID_WIND_BANDS:
        raise SeasonFileError(
            f"{path}.wind.band must be one of {sorted(_VALID_WIND_BANDS)}, got {band!r}"
        )

    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise SeasonFileError(f"{path}.wind.enabled must be a boolean, got {enabled!r}")

    return enabled, band


def _parse_seed(raw: Any, path: str) -> int | None:
    if raw is None:
        return None
    if not isinstance(raw, int):
        raise SeasonFileError(f"{path}.seed must be an integer")
    return raw


def create_races(
    season: Season, declarations: list[RaceDeclaration], *, create_race: Callable[..., Any],
) -> list[Any]:
    """Place each declared race inside its week and create it.

    `create_race` is `racing.models.Race.objects.create`, injected by the
    caller. `schedule/` must not import `racing/` — see
    `schedule/README.md`, *What `schedule/` may import*.

    Uses the injected callable per race, never a bulk operation: `save()` is
    what sets `race_day` and runs the week-containment check, and a bulk
    insert skips `save()` entirely.
    """
    weeks = {w.number: w for w in season.weeks.all()}
    created = []
    for d in declarations:
        week = weeks[d.week]
        starts_at = week.starts_at + timedelta(
            days=DAY_INDEX[d.day], hours=d.time.hour, minutes=d.time.minute,
        )
        created.append(create_race(
            week=week,
            name=d.name,
            course=d.course,
            starts_at=starts_at,
            wind_enabled=d.wind_enabled,
            wind_band=d.wind_band or "",
            seed=d.seed,
            markers=d.markers,
        ))
    return created
