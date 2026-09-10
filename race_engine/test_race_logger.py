"""Tests for RaceLogger's JSONL output, focused on the team metadata map.

Team code + name (see config.py's `race.teams`) are display metadata the
simulation itself never reads, so they are threaded straight from config
through `run_race` into the logger rather than living on `Rider`/`RaceState`.
The logger doesn't need to know their shape at all — it writes whatever
per-team dict it's given verbatim, once per tick line (same as
`course_length`/`segments`), as a `team_id -> {"code": ..., "name": ...}` map.
"""

from __future__ import annotations

import json

from race_engine.models import Course, RaceState, Rider, RiderAttributes, Segment
from race_engine.race_logger import RaceLogger

ATTRS = RiderAttributes(climb=50, sprint=50, flat=50, resistance=50, positioning=50)


def test_logger_writes_team_codes(tmp_path):
    riders = [
        Rider(id="c1", name="C1", attributes=ATTRS, team_id="t1", role="leader"),
        Rider(id="c2", name="C2", attributes=ATTRS, team_id="t2", role="leader"),
    ]
    course = Course(segments=[Segment(length=1000.0, gradient=0.0)])
    state = RaceState.create_initial_state(riders, course)

    log_path = str(tmp_path / "race.jsonl")
    logger = RaceLogger(
        log_path,
        team_codes={
            "t1": {"code": "ALP", "name": "Alpine Racing"},
            "t2": {"code": "SPR", "name": "Sprint Collective"},
        },
    )
    logger.log(state)
    logger.close()

    with open(log_path) as f:
        entry = json.loads(f.readline())

    assert entry["teams"] == {
        "t1": {"code": "ALP", "name": "Alpine Racing"},
        "t2": {"code": "SPR", "name": "Sprint Collective"},
    }


def test_logger_writes_empty_teams_when_absent(tmp_path):
    riders = [Rider(id="c1", name="C1", attributes=ATTRS)]
    course = Course(segments=[Segment(length=1000.0, gradient=0.0)])
    state = RaceState.create_initial_state(riders, course)

    log_path = str(tmp_path / "race.jsonl")
    logger = RaceLogger(log_path)
    logger.log(state)
    logger.close()

    with open(log_path) as f:
        entry = json.loads(f.readline())

    assert entry["teams"] == {}


def test_logger_omits_wind_key_when_disabled(tmp_path):
    riders = [Rider(id="c1", name="C1", attributes=ATTRS)]
    course = Course(segments=[Segment(length=1000.0, gradient=0.0)])
    state = RaceState.create_initial_state(riders, course, wind=False)

    log_path = str(tmp_path / "race.jsonl")
    logger = RaceLogger(log_path)
    logger.log(state)
    logger.close()

    with open(log_path) as f:
        entry = json.loads(f.readline())

    assert "wind" not in entry


def test_logger_writes_wind_object_when_enabled(tmp_path):
    riders = [Rider(id="c1", name="C1", attributes=ATTRS)]
    course = Course(segments=[Segment(length=1000.0, gradient=0.0)])
    state = RaceState.create_initial_state(
        riders, course, wind=True, wind_band="strong", seed=1
    )

    log_path = str(tmp_path / "race.jsonl")
    logger = RaceLogger(log_path)
    logger.log(state)
    logger.close()

    with open(log_path) as f:
        entry = json.loads(f.readline())

    assert "wind" in entry
    assert set(entry["wind"].keys()) == {"speed", "angle", "band"}
    assert entry["wind"]["band"] == "strong"
    assert 0.0 <= entry["wind"]["angle"] < 360.0
    assert entry["wind"]["speed"] >= 0.0

    keys = list(entry.keys())
    assert keys.index("wind") < keys.index("segments")
