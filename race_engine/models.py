from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RiderAttributes:
    climb: int  # 1-100
    sprint: int  # 1-100
    flat: int  # 1-100
    resistance: int  # 1-100, fatigue tolerance

    def __post_init__(self) -> None:
        for attr_name in ("climb", "sprint", "flat", "resistance"):
            val = getattr(self, attr_name)
            if not 1 <= val <= 100:
                raise ValueError(f"{attr_name} must be between 1 and 100, got {val}")


@dataclass
class Rider:
    id: str
    name: str
    attributes: RiderAttributes


@dataclass
class Segment:
    length: float  # meters
    gradient: float  # percentage, positive = uphill


@dataclass
class Course:
    segments: list[Segment]

    @property
    def total_distance(self) -> float:
        return sum(s.length for s in self.segments)


@dataclass
class RiderState:
    rider: Rider
    speed: float = 0.0  # m/s
    position: float = 0.0  # meters from start
    energy: float = 100.0  # 0-100
    stamina: float = 100.0  # 0-100
    finished: bool = False
    finish_time: int | None = None  # seconds


@dataclass
class RaceState:
    course: Course
    rider_states: list[RiderState] = field(default_factory=list)
    current_time: int = 0  # seconds

    @classmethod
    def create_initial_state(
        cls, riders: list[Rider], course: Course
    ) -> RaceState:
        rider_states = [RiderState(rider=r) for r in riders]
        return cls(course=course, rider_states=rider_states, current_time=0)

    def tick(self) -> None:
        from .formulas import (
            apply_energy_modifier,
            compute_base_speed,
            compute_energy_drain,
            compute_stamina_drain,
        )

        for rs in self.rider_states:
            if rs.finished:
                continue

            segment = self._find_segment(rs.position)
            if segment is None:
                rs.finished = True
                rs.finish_time = self.current_time
                continue

            base_speed = compute_base_speed(rs.rider.attributes, segment.gradient)
            rs.speed = apply_energy_modifier(base_speed, rs.energy, rs.stamina)

            rs.position += rs.speed  # 1 tick = 1 second

            energy_drain = compute_energy_drain(
                rs.rider.attributes, segment.gradient, rs.speed
            )
            stamina_drain = compute_stamina_drain(segment.gradient, rs.speed)

            rs.energy = max(0.0, rs.energy - energy_drain)
            rs.stamina = max(0.0, rs.stamina - stamina_drain)

            if rs.position >= self.course.total_distance:
                rs.position = self.course.total_distance
                rs.finished = True
                rs.finish_time = self.current_time

        self.current_time += 1

    def is_finished(self) -> bool:
        return all(rs.finished for rs in self.rider_states)

    def get_results(self) -> list[RiderState]:
        return sorted(
            self.rider_states, key=lambda rs: (rs.finish_time or float("inf"))
        )

    def _find_segment(self, position: float) -> Segment | None:
        offset = 0.0
        for segment in self.course.segments:
            if position < offset + segment.length:
                return segment
            offset += segment.length
        return None


def run_race(
    riders: list[Rider],
    course: Course,
    log_path: str | None = None,
) -> list[RiderState]:
    from .race_logger import RaceLogger

    state = RaceState.create_initial_state(riders, course)
    logger = RaceLogger(log_path) if log_path else None

    try:
        logger.log(state)
        while not state.is_finished():
            state.tick()
            logger.log(state)
    finally:
        if logger:
            logger.close()

    return state.get_results()
