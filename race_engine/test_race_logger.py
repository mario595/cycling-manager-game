"""Tests for RaceLogger's JSONL output, focused on the team-code map.

The team code (a UCI-style 3-letter TV abbreviation, see config.py's
`race.teams`) is display metadata the simulation itself never reads, so it
is threaded straight from config through `run_race` into the logger rather
than living on `Rider`/`RaceState`. It is written once per tick line (same
as `course_length`/`segments`) as a `team_id -> {"code": ...}` map.
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
    logger = RaceLogger(log_path, team_codes={"t1": "ALP", "t2": "SPR"})
    logger.log(state)
    logger.close()

    with open(log_path) as f:
        entry = json.loads(f.readline())

    assert entry["teams"] == {"t1": {"code": "ALP"}, "t2": {"code": "SPR"}}


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
