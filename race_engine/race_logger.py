from __future__ import annotations

import json
from typing import TYPE_CHECKING

import brotli

if TYPE_CHECKING:
    from race_engine.models import RaceState

FORMAT_VERSION = 1
DEFAULT_SAMPLE_INTERVAL = 2
BROTLI_QUALITY = 5


class RaceLogger:
    """Stream a race to a log: one header line, then sampled tick lines.

    Line 1 is a header object holding everything constant for the race — the
    course segments, the team map, each rider's identity, and the sampling
    interval. Every later line is one sample: ``[time, riders, wind?]`` where
    ``time`` is race seconds and ``riders`` is a positional array per rider in
    the same order as ``header.riders`` — the array index *is* the rider
    identity, which is load-bearing (see the plan for #88).

    A sample is written on the first tick, every ``sample_interval`` ticks
    after that, and on any tick where a rider's ``finished`` flag changed —
    so a finish is never invisible, only its exact instant is quantised. The
    first tick is always written because ``state`` is not available until then
    and a t=0 sample is what the player shows before playback starts.

    The file is written brotli-compressed (a `.jsonl.br` file), fed through an
    incremental ``Compressor`` so a race-sized payload is never held twice in
    memory. A stream is only complete after ``close()`` — ``finish()`` writes
    the terminal block.
    """

    def __init__(
        self,
        path: str,
        team_codes: dict[str, dict[str, str]] | None = None,
        sample_interval: int = DEFAULT_SAMPLE_INTERVAL,
    ) -> None:
        self._raw = open(path, "wb")
        self._compressor = brotli.Compressor(quality=BROTLI_QUALITY)
        self._team_codes = team_codes or {}
        self._sample_interval = sample_interval
        self._ticks_seen = 0
        self._last_finished: tuple[bool, ...] | None = None
        self._header_written = False
        self._samples_written = 0

    def log(self, state: RaceState) -> None:
        """Write a sample if this tick is due, is the first tick, or a tick in
        which any rider's finished flag changed. Otherwise do nothing."""
        if not self._header_written:
            self._write_header(state)

        finished = tuple(rs.finished for rs in state.rider_states)
        due = self._ticks_seen % self._sample_interval == 0
        changed = finished != self._last_finished
        self._ticks_seen += 1

        if not (due or changed or self._last_finished is None):
            return

        self._last_finished = finished
        self._write_sample(state)

    @property
    def sample_count(self) -> int:
        return self._samples_written

    @property
    def sample_interval(self) -> int:
        return self._sample_interval

    def close(self) -> None:
        self._raw.write(self._compressor.finish())
        self._raw.close()

    def __enter__(self) -> RaceLogger:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def _emit(self, line: str) -> None:
        chunk = self._compressor.process(line.encode())
        if chunk:
            self._raw.write(chunk)

    def _write_header(self, state: RaceState) -> None:
        header = {
            "v": FORMAT_VERSION,
            "tick_interval": self._sample_interval,
            "course_length": state.course.total_distance,
            "segments": [
                {"length": s.length, "gradient": s.gradient}
                for s in state.course.segments
            ],
            "teams": dict(self._team_codes),
            "riders": [
                {
                    "id": rs.rider.id,
                    "name": rs.rider.name,
                    "team": rs.rider.team_id,
                    "role": rs.rider.role,
                }
                for rs in state.rider_states
            ],
        }
        if state.wind is not None:
            header["wind_band"] = state.wind.band
        self._emit(json.dumps(header) + "\n")
        self._header_written = True

    def _write_sample(self, state: RaceState) -> None:
        riders = [
            [
                round(rs.position, 1),
                round(rs.speed, 2),
                round(rs.energy, 1),
                round(rs.stamina, 1),
                (1 if rs.pulling else 0) | (2 if rs.surging else 0) | (4 if rs.finished else 0),
                rs.finish_time,
            ]
            for rs in state.rider_states
        ]
        # `pos`/`speed`/`energy`/`stamina` are rounded to what a screen can
        # draw; `finish_time` is deliberately not — snapping it to the sample
        # grid would manufacture ties in a bunch sprint.
        sample: list[object] = [state.current_time, riders]
        if state.wind is not None:
            sample.append([round(state.wind.speed, 1), round(state.wind.angle % 360.0, 1)])
        self._emit(json.dumps(sample) + "\n")
        self._samples_written += 1