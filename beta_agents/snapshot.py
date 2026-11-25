"""The harness's own reading of the tester's team, taken at the start of every
visit before the model does anything (#159).

The testers wrote their balance down every visit and never compared it: one
lost $96,000 over fourteen visits while writing "the ledger checks out". So the
harness reads the team itself, saves the reading with the diary entry, and
opens the next visit with what changed, for the tester to account for. The
reading costs game requests only, never a model call.

A reading is plain JSON:

    team              {"id", "code", "name"} or null
    season, week      from the season position, and its `state`
    balance, weekly_wage_bill, fanbase
    riders            {"<id>": "<name>"}
    rank, points      the team's row of the league table, or null

A part the game would not give is {"error": "..."} under the part's name,
which is itself something the tester may report. The visit goes on.
"""

from __future__ import annotations

from typing import Any

from .game_api import GameAPI, GameAPIError, Response


def take(api: GameAPI) -> dict:
    reading: dict[str, Any] = {}
    errors: dict[str, str] = {}

    def get(part: str, path: str) -> Any | None:
        try:
            response: Response = api.call("GET", path)
        except GameAPIError as error:
            errors[part] = str(error)[:200]
            return None
        if response.status != 200 or not isinstance(response.body, dict):
            errors[part] = f"GET {path} answered {response.status}: {str(response.body)[:150]}"
            return None
        return response.body

    me = get("team", "/api/accounts/me/")
    team = (me or {}).get("team") if me is not None else None
    reading["team"] = {k: team.get(k) for k in ("id", "code", "name")} if isinstance(team, dict) else None

    position = get("position", "/api/schedule/position/")
    if position is not None:
        reading["state"] = position.get("state")
        reading["season"] = position.get("season")
        reading["week"] = position.get("week")

    if reading["team"] is not None:
        finances = get("finances", "/api/economy/finances/")
        if finances is not None:
            for key in ("balance", "weekly_wage_bill", "fanbase"):
                reading[key] = finances.get(key)
        roster = get("roster", "/api/riders/")
        if roster is not None:
            reading["riders"] = {str(r.get("id")): r.get("name") for r in roster.get("riders") or [] if isinstance(r, dict)}
        standings = get("standings", "/api/competitions/standings/")
        if standings is not None:
            row = next(
                (r for r in standings.get("standings") or [] if isinstance(r, dict) and (r.get("team") or {}).get("id") == reading["team"]["id"]),
                None,
            )
            reading["rank"] = row.get("rank") if row else None
            reading["points"] = row.get("points") if row else None
    if errors:
        reading["errors"] = errors
    return reading


def describe_current(current: dict) -> list[str]:
    """The reading on its own, for a visit with nothing to compare with."""
    lines = [_team_line(current.get("team")), _when(current)]
    if current.get("team") is not None:
        if "balance" in current:
            lines.append(f"balance {_money(current.get('balance'))}, weekly wage bill {_money(current.get('weekly_wage_bill'))}, fanbase {_num(current.get('fanbase'))}")
        if "riders" in current:
            lines.append(f"roster: {len(current['riders'])} riders")
        if "rank" in current:
            lines.append(f"league: {_rank(current.get('rank'))}, {_num(current.get('points'))} points")
    lines += _error_lines(current)
    return [line for line in lines if line]


def describe_changes(previous: dict | None, current: dict) -> list[str]:
    """What moved between the last visit's reading and this one, one plain line
    per thing. Without a previous reading, or after a change of team, there is
    nothing to compare, and the lines say so."""
    if previous is None:
        return ["No reading from your last visit to compare with. The team now:"] + describe_current(current)
    old_team, new_team = previous.get("team"), current.get("team")
    if (old_team or {}).get("id") != (new_team or {}).get("id"):
        return [f"You managed {_team_name(old_team)} last visit, and now {_team_name(new_team)}, so nothing is compared. The team now:"] + describe_current(current)

    lines = [f"{_when(previous)} → {_when(current)}"]
    if new_team is None:
        return lines + _error_lines(current)
    for key, label, fmt in (
        ("balance", "balance", _money),
        ("weekly_wage_bill", "weekly wage bill", _money),
        ("fanbase", "fanbase", _num),
        ("points", "league points", _num),
    ):
        if _readable(previous, current, key):
            lines.append(_from_to(label, previous.get(key), current.get(key), fmt))
    if _readable(previous, current, "rank"):
        lines.append(f"league position: {_rank(previous.get('rank'))} → {_rank(current.get('rank'))}")
    if _readable(previous, current, "riders"):
        old, new = previous["riders"] or {}, current["riders"] or {}
        line = f"roster: {len(old)} → {len(new)} riders"
        joined = [f"{new[i]} ({i})" for i in new if i not in old]
        left = [f"{old[i]} ({i})" for i in old if i not in new]
        if joined:
            line += "; joined: " + ", ".join(joined)
        if left:
            line += "; left: " + ", ".join(left)
        lines.append(line)
    for part, error in sorted((previous.get("errors") or {}).items()):
        if part not in (current.get("errors") or {}):
            lines.append(f"{part}: could not be read last visit ({error}), so it is not compared")
    return lines + _error_lines(current)


def _readable(previous: dict, current: dict, key: str) -> bool:
    return key in previous and key in current


def _from_to(label: str, old: Any, new: Any, fmt) -> str:
    line = f"{label}: {fmt(old)} → {fmt(new)}"
    if isinstance(old, int) and isinstance(new, int) and not isinstance(old, bool):
        diff = new - old
        if fmt is _money:
            line += f" ({'+' if diff >= 0 else '-'}${abs(diff):,})"
        else:
            line += f" ({diff:+,})"
    return line


def _error_lines(reading: dict) -> list[str]:
    return [f"{part}: could not be read ({error})" for part, error in sorted((reading.get("errors") or {}).items())]


def _when(reading: dict) -> str:
    if reading.get("season") is None:
        return f"no season running ({reading.get('state') or 'unknown'})"
    return f"Season {reading.get('season')} Week {reading.get('week')}"


def _team_line(team: dict | None) -> str:
    return f"team: {_team_name(team)}"


def _team_name(team: dict | None) -> str:
    if not team:
        return "no team"
    return f"{team.get('name')} ({team.get('code')}, id {team.get('id')})"


def _money(value: Any) -> str:
    return f"${value:,}" if isinstance(value, int) else "unknown"


def _num(value: Any) -> str:
    return f"{value:,}" if isinstance(value, int) else "unknown"


def _rank(value: Any) -> str:
    if not isinstance(value, int):
        return "not in the table"
    suffix = "th" if 10 <= value % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(value % 10, "th")
    return f"{value}{suffix}"
