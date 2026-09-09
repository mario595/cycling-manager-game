"""Tests for team/role config parsing and validation.

Covers the Team Tactics Tier A groundwork (see TEAM_TACTICS_PLAN.md): `team`
and `role` are optional per rider, defaulting to a team-of-one leader so
existing configs and hand-built `Rider` objects keep working unchanged, and
exactly one leader per team is enforced at load time.
"""

from __future__ import annotations

import json

import pytest

from race_engine.config import ConfigError, load_config
from race_engine.models import Rider, RiderAttributes

ATTRS = {"climb": 50, "sprint": 50, "flat": 50, "resistance": 50, "positioning": 50}


def _rider(rid: str, team: str | None = None, role: str | None = None) -> dict:
    raw = {"id": rid, "name": rid, "attributes": ATTRS}
    if team is not None:
        raw["team"] = team
    if role is not None:
        raw["role"] = role
    return raw


def _config(riders: list[dict]) -> dict:
    return {
        "race": {
            "course": [{"length": 1000.0, "gradient": 0.0}],
            "riders": riders,
        }
    }


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
