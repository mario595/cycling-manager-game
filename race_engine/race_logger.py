from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from race_engine.models import RaceState


class RaceLogger:
    def __init__(self, path: str, team_codes: dict[str, dict[str, str]] | None = None) -> None:
        self._file = open(path, "w")
        self._team_codes = team_codes or {}

    def log(self, state: RaceState) -> None:
        entry = {
            "time": state.current_time,
            "course_length": state.course.total_distance,
        }
        if state.wind is not None:
            entry["wind"] = {
                "speed": round(state.wind.speed, 1),
                "angle": round(state.wind.angle % 360.0, 1),
                "band": state.wind.band,
            }
        entry.update({
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
                    "pos": round(rs.position, 2),
                    "speed": round(rs.speed, 2),
                    "energy": round(rs.energy, 2),
                    "stamina": round(rs.stamina, 2),
                    "pulling": rs.pulling,
                    "surging": rs.surging,
                    "finished": rs.finished,
                    "finish_time": rs.finish_time,
                }
                for rs in state.rider_states
            ],
        })
        self._file.write(json.dumps(entry) + "\n")
        self._file.flush()

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> RaceLogger:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
