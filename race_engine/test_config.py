"""Tests for team/role/team-code config parsing and validation.

Covers the Team Tactics Tier A groundwork (see TEAM_TACTICS_PLAN.md): `team`
and `role` are optional per rider, defaulting to a team-of-one leader so
existing configs and hand-built `Rider` objects keep working unchanged, and
exactly one leader per team is enforced at load time. Also covers the
optional `race.teams` map of team code + name (the TV-style team abbreviation
plus its full display name), which is display metadata validated at load
time but absent by default.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from race_engine.config import ConfigError, load_config
from race_engine.models import Rider, RiderAttributes

ATTRS = {"climb": 50, "sprint": 50, "flat": 50, "resistance": 50, "positioning": 50}
_CONFIGS_DIR = Path(__file__).parent / "configs"


def _rider(rid: str, team: str | None = None, role: str | None = None) -> dict:
    raw = {"id": rid, "name": rid, "attributes": ATTRS}
    if team is not None:
        raw["team"] = team
    if role is not None:
        raw["role"] = role
    return raw


def _config(riders: list[dict], teams: dict | None = None, wind: dict | None = None) -> dict:
    race: dict = {
        "course": [{"length": 1000.0, "gradient": 0.0}],
        "riders": riders,
    }
    if teams is not None:
        race["teams"] = teams
    if wind is not None:
        race["wind"] = wind
    return {"race": race}


def _write(tmp_path, cfg: dict) -> str:
    path = tmp_path / "config.json"
    path.write_text(json.dumps(cfg))
    return str(path)


def test_rider_defaults_team_of_one_leader():
    r = Rider(id="c1", name="C1", attributes=RiderAttributes(**ATTRS))
    assert r.team_id == "c1"
    assert r.role == "leader"


def test_config_defaults_team_and_role_when_absent(tmp_path):
    cfg = _config([_rider("c1"), _rider("c2")])
    result = load_config(_write(tmp_path, cfg))
    riders = {r.id: r for r in result["riders"]}
    assert riders["c1"].team_id == "c1"
    assert riders["c1"].role == "leader"
    assert riders["c2"].team_id == "c2"
    assert riders["c2"].role == "leader"


def test_config_parses_team_and_role(tmp_path):
    cfg = _config(
        [
            _rider("c1", team="t1", role="leader"),
            _rider("c2", team="t1", role="support"),
        ]
    )
    result = load_config(_write(tmp_path, cfg))
    riders = {r.id: r for r in result["riders"]}
    assert riders["c1"].team_id == "t1"
    assert riders["c1"].role == "leader"
    assert riders["c2"].team_id == "t1"
    assert riders["c2"].role == "support"


def test_config_rejects_invalid_role(tmp_path):
    cfg = _config([_rider("c1", team="t1", role="captain")])
    with pytest.raises(ConfigError, match="role"):
        load_config(_write(tmp_path, cfg))


def test_config_rejects_team_with_two_leaders(tmp_path):
    cfg = _config(
        [
            _rider("c1", team="t1", role="leader"),
            _rider("c2", team="t1", role="leader"),
        ]
    )
    with pytest.raises(ConfigError, match="2 leaders"):
        load_config(_write(tmp_path, cfg))


def test_config_rejects_team_with_zero_leaders(tmp_path):
    cfg = _config(
        [
            _rider("c1", team="t1", role="support"),
            _rider("c2", team="t1", role="support"),
        ]
    )
    with pytest.raises(ConfigError, match="no leader"):
        load_config(_write(tmp_path, cfg))


def test_config_defaults_team_codes_to_empty_when_absent(tmp_path):
    cfg = _config([_rider("c1")])
    result = load_config(_write(tmp_path, cfg))
    assert result["team_codes"] == {}


def test_config_parses_team_codes(tmp_path):
    cfg = _config(
        [_rider("c1", team="t1"), _rider("c2", team="t2")],
        teams={
            "t1": {"code": "ALP", "name": "Alpine Racing"},
            "t2": {"code": "SPR", "name": "Sprint Collective"},
        },
    )
    result = load_config(_write(tmp_path, cfg))
    assert result["team_codes"] == {
        "t1": {"code": "ALP", "name": "Alpine Racing"},
        "t2": {"code": "SPR", "name": "Sprint Collective"},
    }


def test_config_rejects_team_code_wrong_length(tmp_path):
    cfg = _config(
        [_rider("c1", team="t1")],
        teams={"t1": {"code": "AL", "name": "Alpine Racing"}},
    )
    with pytest.raises(ConfigError, match="3 uppercase letters"):
        load_config(_write(tmp_path, cfg))


def test_config_rejects_team_code_lowercase(tmp_path):
    cfg = _config(
        [_rider("c1", team="t1")],
        teams={"t1": {"code": "alp", "name": "Alpine Racing"}},
    )
    with pytest.raises(ConfigError, match="3 uppercase letters"):
        load_config(_write(tmp_path, cfg))


def test_config_rejects_duplicate_team_codes(tmp_path):
    cfg = _config(
        [_rider("c1", team="t1"), _rider("c2", team="t2")],
        teams={
            "t1": {"code": "ALP", "name": "Alpine Racing"},
            "t2": {"code": "ALP", "name": "Alpine Racing Reserves"},
        },
    )
    with pytest.raises(ConfigError, match="unique"):
        load_config(_write(tmp_path, cfg))


def test_config_rejects_team_missing_name(tmp_path):
    cfg = _config([_rider("c1", team="t1")], teams={"t1": {"code": "ALP"}})
    with pytest.raises(ConfigError, match="name"):
        load_config(_write(tmp_path, cfg))


def test_config_rejects_team_empty_name(tmp_path):
    cfg = _config(
        [_rider("c1", team="t1")],
        teams={"t1": {"code": "ALP", "name": "   "}},
    )
    with pytest.raises(ConfigError, match="name"):
        load_config(_write(tmp_path, cfg))


def test_config_defaults_wind_enabled_with_no_forced_band_when_absent(tmp_path):
    cfg = _config([_rider("c1")])
    result = load_config(_write(tmp_path, cfg))
    assert result["wind_enabled"] is True
    assert result["wind_band"] is None


def test_config_parses_forced_wind_band(tmp_path):
    cfg = _config([_rider("c1")], wind={"band": "strong"})
    result = load_config(_write(tmp_path, cfg))
    assert result["wind_enabled"] is True
    assert result["wind_band"] == "strong"


def test_config_parses_wind_disabled(tmp_path):
    cfg = _config([_rider("c1")], wind={"enabled": False})
    result = load_config(_write(tmp_path, cfg))
    assert result["wind_enabled"] is False


def test_config_rejects_unknown_wind_band(tmp_path):
    cfg = _config([_rider("c1")], wind={"band": "hurricane"})
    with pytest.raises(ConfigError, match="band"):
        load_config(_write(tmp_path, cfg))


def test_config_rejects_non_bool_wind_enabled(tmp_path):
    cfg = _config([_rider("c1")], wind={"enabled": "yes"})
    with pytest.raises(ConfigError, match="enabled"):
        load_config(_write(tmp_path, cfg))


def test_grand_field_config_loads_sixty_four_riders_in_sixteen_teams():
    # load_config succeeding already validates one leader per team and
    # unique team codes (RaceSetupError/ConfigError otherwise).
    result = load_config(str(_CONFIGS_DIR / "grand_field.json"))
    assert len(result["riders"]) == 64
    assert len({r.team_id for r in result["riders"]}) == 16
    assert result["course"].total_distance == 200_000.0
