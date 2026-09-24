"""Tests for RaceLogger's header + sampled, positional format.

The log is one header line (everything constant for the race) followed by
sampled tick lines; each rider's changing state is a positional array in the
same order as `header.riders`, so the array index *is* the rider identity —
an order drift silently swaps identities mid-race, which is why the header
and every sample must iterate `state.rider_states` alike.
"""

from __future__ import annotations

import json
import random

import brotli
import pytest

from race_engine.models import Course, RaceState, Rider, RiderAttributes, Segment
from race_engine.race_logger import FORMAT_VERSION, RaceLogger

ATTRS = RiderAttributes(climb=50, sprint=50, flat=50, resistance=50, positioning=50)


def _state(riders, *, wind=True, wind_band=None) -> RaceState:
    course = Course(segments=[Segment(length=1000.0, gradient=0.0)])
    return RaceState.create_initial_state(riders, course, wind=wind, wind_band=wind_band)


def _lines(log_path) -> list:
    with open(log_path, "rb") as f:
        data = f.read()
    return [json.loads(line) for line in brotli.decompress(data).decode().splitlines()]


def test_header_carries_static_metadata_once(tmp_path):
    riders = [
        Rider(id="c1", name="C1", attributes=ATTRS, team_id="t1", role="leader"),
        Rider(id="c2", name="C2", attributes=ATTRS, team_id="t2", role="support"),
    ]
    state = _state(riders, wind=False)
    state.rider_states[0].position = 100.0
    state.rider_states[1].position = 50.0

    log_path = str(tmp_path / "race.jsonl")
    logger = RaceLogger(
        log_path,
        team_codes={
            "t1": {"code": "ALP", "name": "Alpine Racing", "colour": "#1d56c9"},
            "t2": {"code": "SPR", "name": "Sprint Collective", "colour": "#e26912"},
        },
    )
    logger.log(state)
    logger.close()

    lines = _lines(log_path)
    assert len(lines) == 2
    header, sample = lines

    assert header["v"] == FORMAT_VERSION
    assert header["tick_interval"] == 2
    assert header["course_length"] == 1000.0
    assert header["segments"] == [{"length": 1000.0, "gradient": 0.0}]
    assert header["teams"] == {
        "t1": {"code": "ALP", "name": "Alpine Racing", "colour": "#1d56c9"},
        "t2": {"code": "SPR", "name": "Sprint Collective", "colour": "#e26912"},
    }
    assert header["riders"] == [
        {"id": "c1", "name": "C1", "team": "t1", "role": "leader"},
        {"id": "c2", "name": "C2", "team": "t2", "role": "support"},
    ]
    # Header rider order and first sample's array order must agree — the
    # array index is the rider identity.
    assert [line[0] for line in sample[1]] == [100.0, 50.0]


def test_empty_teams_written_when_absent(tmp_path):
    state = _state([Rider(id="c1", name="C1", attributes=ATTRS)], wind=False)

    log_path = str(tmp_path / "race.jsonl")
    logger = RaceLogger(log_path)
    logger.log(state)
    logger.close()

    assert _lines(log_path)[0]["teams"] == {}


def test_ten_tick_race_at_interval_two_writes_six_lines(tmp_path):
    course = Course(segments=[Segment(length=500000.0, gradient=0.0)])
    state = RaceState.create_initial_state(
        [Rider(id="c1", name="C1", attributes=ATTRS)], course, wind=False
    )

    log_path = str(tmp_path / "race.jsonl")
    logger = RaceLogger(log_path)
    logger.log(state)
    for _ in range(9):
        state.tick()
        logger.log(state)
    logger.close()

    lines = _lines(log_path)
    # Header + samples at ticks 0, 2, 4, 6, 8 — not every tick, and not the
    # whole 10-tick race.
    assert len(lines) == 6
    assert [sample[0] for sample in lines[1:]] == [0, 2, 4, 6, 8]


def test_flags_pack_into_a_bitfield(tmp_path):
    riders = [
        Rider(id=f"r{i}", name=f"R{i}", attributes=ATTRS) for i in range(5)
    ]
    state = _state(riders, wind=False)
    bit_settings = [
        (0, ()),
        (1, ("pulling",)),
        (2, ("surging",)),
        (4, ("finished",)),
        (7, ("pulling", "surging", "finished")),
    ]
    for rs, (_, bit_names) in zip(state.rider_states, bit_settings):
        for name in bit_names:
            setattr(rs, name, True)

    log_path = str(tmp_path / "race.jsonl")
    logger = RaceLogger(log_path)
    logger.log(state)
    logger.close()

    sample = _lines(log_path)[1]
    packed = [rider[4] for rider in sample[1]]
    assert packed == [0, 1, 2, 4, 7]


def test_finish_off_the_sample_grid_is_still_written(tmp_path):
    course = Course(segments=[Segment(length=500000.0, gradient=0.0)])
    state = RaceState.create_initial_state(
        [Rider(id="c1", name="C1", attributes=ATTRS)], course, wind=False
    )

    log_path = str(tmp_path / "race.jsonl")
    logger = RaceLogger(log_path)
    logger.log(state)
    for _ in range(3):
        state.tick()
        logger.log(state)

    # The flag change happens on an odd tick — off the every-2s grid. The
    # logger must still write it, and the exact finish_time must pass through
    # unrounded and unsnapped (decision 6 of the plan: never round it).
    assert state.current_time == 3
    state.rider_states[0].finished = True
    state.rider_states[0].finish_time = 1737.17
    logger.log(state)
    logger.close()

    lines = _lines(log_path)
    assert [sample[0] for sample in lines[1:]] == [0, 2, 3]
    finish_sample = lines[-1]
    rider = finish_sample[1][0]
    assert finish_sample[0] == 3
    assert rider[4] & 4  # finished flag
    assert rider[5] == 1737.17


def test_dnf_sets_flag_bit_eight(tmp_path):
    riders = [
        Rider(id="r0", name="R0", attributes=ATTRS),
        Rider(id="r1", name="R1", attributes=ATTRS),
    ]
    state = _state(riders, wind=False)
    state.rider_states[1].dnf = True

    log_path = str(tmp_path / "race.jsonl")
    logger = RaceLogger(log_path)
    logger.log(state)
    logger.close()

    sample = _lines(log_path)[1]
    packed = [rider[4] for rider in sample[1]]
    assert packed == [0, 8]


def test_dnf_off_the_sample_grid_is_still_written(tmp_path):
    course = Course(segments=[Segment(length=500000.0, gradient=0.0)])
    state = RaceState.create_initial_state(
        [Rider(id="c1", name="C1", attributes=ATTRS)], course, wind=False
    )

    log_path = str(tmp_path / "race.jsonl")
    logger = RaceLogger(log_path)
    logger.log(state)
    # tick() draws from the global random module for speed jitter; save and
    # restore it so this test's ticks don't perturb any other, unrelated
    # test's unseeded use of the same stream.
    saved_random_state = random.getstate()
    for _ in range(3):
        state.tick()
        logger.log(state)
    random.setstate(saved_random_state)

    # DNF flips on an odd tick — off the every-2s grid. It changes no
    # `finished` flag, so tracking (finished, dnf) pairs is what forces a
    # sample here; tracking `finished` alone would miss it.
    assert state.current_time == 3
    state.rider_states[0].dnf = True
    logger.log(state)
    logger.close()

    lines = _lines(log_path)
    assert [sample[0] for sample in lines[1:]] == [0, 2, 3]
    dnf_sample = lines[-1]
    rider = dnf_sample[1][0]
    assert dnf_sample[0] == 3
    assert rider[4] & 8  # dnf flag


def test_wind_band_goes_to_header_and_speed_angle_per_tick(tmp_path):
    state = _state(
        [Rider(id="c1", name="C1", attributes=ATTRS)],
        wind=True, wind_band="moderate",
    )

    log_path = str(tmp_path / "race.jsonl")
    logger = RaceLogger(log_path)
    logger.log(state)
    logger.close()

    header, sample = _lines(log_path)
    assert header["wind_band"] == "moderate"
    assert len(sample) == 3
    speed, angle = sample[2]
    assert round(speed, 1) == speed
    assert 0.0 <= angle < 360.0
    assert round(angle, 1) == angle


def test_wind_absent_entirely_when_disabled(tmp_path):
    state = _state([Rider(id="c1", name="C1", attributes=ATTRS)], wind=False)

    log_path = str(tmp_path / "race.jsonl")
    logger = RaceLogger(log_path)
    logger.log(state)
    logger.close()

    header, sample = _lines(log_path)
    assert "wind_band" not in header
    assert len(sample) == 2


def test_sample_count_counts_written_samples(tmp_path):
    state = _state([Rider(id="c1", name="C1", attributes=ATTRS)], wind=False)

    log_path = str(tmp_path / "race.jsonl")
    logger = RaceLogger(log_path)
    logger.log(state)
    assert logger.sample_count == 1
    logger.close()


def test_file_is_brotli_and_round_trips_to_the_same_lines(tmp_path):
    state = _state(
        [
            Rider(id="c1", name="C1", attributes=ATTRS, team_id="t1", role="leader"),
            Rider(id="c2", name="C2", attributes=ATTRS, team_id="t2", role="support"),
        ],
        wind=True, wind_band="light",
    )

    log_path = str(tmp_path / "race.jsonl")
    logger = RaceLogger(log_path, team_codes={"t1": {"code": "ALP", "name": "Alpine Racing"}})
    logger.log(state)
    logger.close()

    with open(log_path, "rb") as f:
        raw = f.read()
    # The bytes on disk must not be plain JSON text — they are compressed.
    assert b'"v"' not in raw
    lines = _lines(log_path)
    header, sample = lines
    assert header["v"] == FORMAT_VERSION
    assert header["tick_interval"] == 2
    assert header["teams"] == {"t1": {"code": "ALP", "name": "Alpine Racing"}}
    assert header["wind_band"] == "light"
    assert [r[4] for r in sample[1]] == [0, 0]  # neither rider pulling/surging/finished
    assert sample[0] == 0


def test_stream_is_incomplete_before_close(tmp_path):
    state = _state([Rider(id="c1", name="C1", attributes=ATTRS)], wind=False)

    log_path = str(tmp_path / "race.jsonl")
    logger = RaceLogger(log_path)
    logger.log(state)

    with open(log_path, "rb") as f:
        data = f.read()
    with pytest.raises(brotli.error):
        brotli.decompress(data)

    logger.close()
    with open(log_path, "rb") as f:
        data = f.read()
    assert _lines(log_path)[1][0] == 0