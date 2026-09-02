from __future__ import annotations

import json
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from race_engine.models import RaceState


class RaceLogger:
    def __init__(self, path: str) -> None:
        self._file = open(path, "w")

    def log(self, state: RaceState) -> None:
        entry = {
            "time": state.current_time,
            "course_length": state.course.total_distance,
            "segments": [
                {"length": s.length, "gradient": s.gradient}
                for s in state.course.segments
            ],
            "riders": [
                {
                    "id": rs.rider.id,
                    "name": rs.rider.name,
                    "pos": round(rs.position, 2),
                    "speed": round(rs.speed, 2),
                    "energy": round(rs.energy, 2),
                    "stamina": round(rs.stamina, 2),
                    "drafting": rs.drafting,
                    "pulling": rs.pulling,
                    "finished": rs.finished,
                    "finish_time": rs.finish_time,
                }
                for rs in state.rider_states
            ],
        }
        self._file.write(json.dumps(entry) + "\n")
        self._file.flush()

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> RaceLogger:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
