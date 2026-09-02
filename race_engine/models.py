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
    drafting: bool = False  # currently drafting behind another rider
    pulling: bool = False  # currently pulling (has riders drafting behind)
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
            DRAFT_DISTANCE,
            add_speed_jitter,
            apply_energy_modifier,
            compute_base_speed,
            compute_energy_drain,
            compute_stamina_drain,
            draft_discount,
        )

        # Phase 1: snapshot positions and compute deltas using pre-tick state.
        positions = [rs.position for rs in self.rider_states]
        # Indices ordered by position, descending (front first).
        sorted_idx = sorted(
            range(len(self.rider_states)),
            key=lambda i: positions[i],
            reverse=True,
        )

        deltas = [None] * len(self.rider_states)  # (speed, energy_delta, stamina, drafting, pulling)

        for i, rs in enumerate(self.rider_states):
            if rs.finished:
                continue

            segment = self._find_segment(rs.position)
            if segment is None:
                # Past the finish line.
                deltas[i] = (0.0, 0.0, 0.0, False, False)
                continue

            drafting = self._is_drafting(i, positions, sorted_idx, segment.gradient)
            pulling = self._is_pulling(i, positions, sorted_idx, segment.gradient)
            base_speed = compute_base_speed(rs.rider.attributes, segment.gradient)
            speed = apply_energy_modifier(base_speed, rs.energy, rs.stamina)
            speed = add_speed_jitter(speed)

            draft = draft_discount(segment.gradient) if drafting else 1.0
            energy_drain = compute_energy_drain(
                rs.rider.attributes, segment.gradient, speed, draft
            )
            stamina_drain = compute_stamina_drain(segment.gradient, speed)

            deltas[i] = (speed, energy_drain, stamina_drain, drafting, pulling)

        # Phase 2: apply all deltas consistently.
        for i, rs in enumerate(self.rider_states):
            if rs.finished:
                continue

            delta = deltas[i]
            if delta is None:
                continue

            speed, energy_drain, stamina_drain, drafting, pulling = delta
            rs.speed = speed
            rs.drafting = drafting
            rs.pulling = pulling

            rs.position += speed  # 1 tick = 1 second

            rs.energy = max(0.0, rs.energy - energy_drain)
            rs.stamina = max(0.0, rs.stamina - stamina_drain)

            if rs.position >= self.course.total_distance:
                rs.position = self.course.total_distance
                rs.finished = True
                rs.finish_time = self.current_time

        self.current_time += 1

    def _is_drafting(
        self,
        idx: int,
        positions: list[float],
        sorted_idx: list[int],
        gradient: float,
    ) -> bool:
        """True if another rider is within DRAFT_DISTANCE ahead of this rider.

        position (meters from start) is higher for the rider who is ahead,
        i.e. the leader. sorted_idx is ordered by position descending.
        """
        from .formulas import DRAFT_DISTANCE, DRAFT_UPHILL_LIMIT

        pos = positions[idx]

        if gradient > DRAFT_UPHILL_LIMIT:
            return False

        for other in sorted_idx:
            if other == idx:
                continue
            diff = positions[other] - pos
            if diff >= 0 and diff <= DRAFT_DISTANCE:
                return True
        return False

    def _is_pulling(
        self,
        idx: int,
        positions: list[float],
        sorted_idx: list[int],
        gradient: float,
    ) -> bool:
        """True if this rider is on the front of a group (pulling the bunch).

        A rider pulls only when they are NOT drafting (no one ahead within
        DRAFT_DISTANCE) and there is someone behind them within DRAFT_DISTANCE.
        Riders in the middle of a group are drafting, not pulling.
        """
        from .formulas import DRAFT_DISTANCE, DRAFT_UPHILL_LIMIT

        pos = positions[idx]

        if gradient > DRAFT_UPHILL_LIMIT:
            return False

        # Not on the front if someone is drafting ahead of this rider.
        if self._is_drafting(idx, positions, sorted_idx, gradient):
            return False

        # On the front only if someone is within draft distance behind.
        for other in sorted_idx:
            if other == idx:
                continue
            diff = pos - positions[other]
            if diff > 0 and diff <= DRAFT_DISTANCE:
                return True
        return False

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
        if logger:
            logger.log(state)
        while not state.is_finished():
            state.tick()
            if logger:
                logger.log(state)
    finally:
        if logger:
            logger.close()

    return state.get_results()
