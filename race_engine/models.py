from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RiderAttributes:
    climb: int  # 1-100
    sprint: int  # 1-100
    flat: int  # 1-100
    resistance: int  # 1-100, fatigue tolerance
    positioning: int  # 1-100, draft/shelter skill

    def __post_init__(self) -> None:
        for attr_name in ("climb", "sprint", "flat", "resistance", "positioning"):
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
    surging: bool = False  # currently in an energy-burst effort
    surge_ticks: int = 0  # remaining ticks of the current surge
    surge_cooldown: int = 0  # ticks before another surge may start
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
            DRAFT_UPHILL_LIMIT,
            SURGE_ENERGY_COST,
            SURGE_SPEED_BOOST,
            add_speed_jitter,
            apply_energy_burst_modifier,
            apply_stamina_cruise_modifier,
            compute_base_speed,
            compute_draft_factors,
            compute_energy_drain,
            compute_stamina_drain,
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
        gradients = [0.0] * len(self.rider_states)
        own_speeds = [0.0] * len(self.rider_states)

        for i, rs in enumerate(self.rider_states):
            if rs.finished:
                continue

            segment = self._find_segment(rs.position)
            if segment is None:
                # Past the finish line.
                deltas[i] = (0.0, 0.0, 0.0, False, False)
                continue

            gradients[i] = segment.gradient
            # Natural cruise pace — base speed throttled by stamina (cracking),
            # before any energy/burst considerations.
            cruise = apply_stamina_cruise_modifier(
                compute_base_speed(rs.rider.attributes, segment.gradient), rs.stamina
            )
            own_speeds[i] = add_speed_jitter(cruise)

        # Decide this tick whether any rider starts an energy surge (attack a
        # climb, chase a gap, or launch the finish sprint).
        self._decide_surges(positions, sorted_idx, gradients)

        # Resolve pack cohesion: riders within PACK_COHESION_DISTANCE of each other on
        # draft-allowed terrain cohere into a peloton that rolls at a shared,
        # controlled sustainable tempo rather than each at their own maximal
        # pace. A rider whose own cruise falls below the tempo is DROPPED
        # (cannot stay sheltered), so a fatigued rider doesn't drag the pack.
        # Riders currently surging break from the pack and ride their own pace.
        #
        # Packs are connected components over (undirected) proximity within
        # PACK_COHESION_DISTANCE. Found via BFS to avoid cycle risk.
        from .formulas import GROUP_DROP_FRACTION, PACK_COHESION_DISTANCE

        active = [
            i
            for i in range(len(self.rider_states))
            if deltas[i] is None and self.rider_states[i].surge_ticks == 0
        ]

        # adjacency: rider i is adjacent to any rider within PACK_COHESION_DISTANCE
        # ahead on a draft-allowed gradient (propagated pairwise, not via the
        # strict 3m wheel-to-wheel drafting distance).
        adj: dict[int, list[int]] = {i: [] for i in active}
        sorted_ahead: dict[int, list[int]] = {}
        for i in active:
            gradient = gradients[i]
            if gradient > DRAFT_UPHILL_LIMIT:
                continue
            pos = positions[i]
            near = [
                j
                for j in sorted_idx
                if j in adj
                and j != i
                and not self.rider_states[j].finished
                and 0 <= positions[j] - pos <= PACK_COHESION_DISTANCE
            ]
            for j in near:
                adj[i].append(j)
                adj[j].append(i)

        # union active riders into packs via BFS over undirected adjacency
        packs: list[list[int]] = []
        seen: set[int] = set()
        for start in active:
            if start in seen:
                continue
            comp: list[int] = []
            stack = [start]
            seen.add(start)
            while stack:
                cur = stack.pop()
                comp.append(cur)
                for nb in adj.get(cur, []):
                    if nb in active and nb not in seen:
                        seen.add(nb)
                        stack.append(nb)
            packs.append(comp)

        effective_speeds = list(own_speeds)
        drafting_flags = [False] * len(self.rider_states)
        pack_depth = [0.0] * len(self.rider_states)

        # A pack of a single rider rides alone at their own cruise.
        for pack in packs:
            if len(pack) < 2:
                continue
            member_speeds = [own_speeds[m] for m in pack]
            best = max(member_speeds)
            pace = best * GROUP_DROP_FRACTION
            coherent = [m for m in pack if own_speeds[m] >= pace]
            # depth = how many coherent riders sit ahead (sheltering this rider)
            coherent_by_pos = sorted(coherent, key=lambda m: positions[m], reverse=True)
            depth_of: dict[int, int] = {}
            for d, m in enumerate(coherent_by_pos):
                depth_of[m] = d  # 0 = pulling front, 1 = first wheel, ...
            for m in coherent:
                drafting_flags[m] = self._is_drafting(
                    m, positions, sorted_idx, gradients[m]
                )
                effective_speeds[m] = pace
                pack_depth[m] = float(depth_of[m])

        for i, rs in enumerate(self.rider_states):
            if rs.finished or deltas[i] is not None:
                continue

            drafting = drafting_flags[i]
            pulling = self._is_pulling(i, positions, sorted_idx, gradients[i])
            draft_stamina_factor, draft_energy_factor = compute_draft_factors(
                rs.rider.attributes.positioning, pack_depth[i]
            )

            if rs.surge_ticks > 0:
                # Active surge: ride boosted own speed, burn extra energy.
                surge_speed = own_speeds[i] * (1.0 + SURGE_SPEED_BOOST)
                effective = add_speed_jitter(
                    apply_energy_burst_modifier(surge_speed, rs.energy)
                )
                energy_drain = compute_energy_drain(
                    gradients[i], effective, own_speeds[i], draft_energy_factor
                ) + SURGE_ENERGY_COST
                rs.surge_ticks -= 1
            else:
                # Adopted group pace, with the rider's energy-burst throttle.
                group_pace = effective_speeds[i]
                effective = add_speed_jitter(
                    apply_energy_burst_modifier(group_pace, rs.energy)
                )
                energy_drain = compute_energy_drain(
                    gradients[i], effective, own_speeds[i], draft_energy_factor
                )

            stamina_drain = compute_stamina_drain(
                gradients[i], effective, draft_stamina_factor,
                rs.rider.attributes.resistance,
            )

            if rs.surge_cooldown > 0:
                rs.surge_cooldown -= 1

            deltas[i] = (effective, energy_drain, stamina_drain, drafting, pulling)

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
            rs.surging = rs.surge_ticks > 0

            rs.position += speed  # 1 tick = 1 second

            rs.energy = max(0.0, min(100.0, rs.energy - energy_drain))
            rs.stamina = max(0.0, min(100.0, rs.stamina - stamina_drain))

            if rs.position >= self.course.total_distance:
                rs.position = self.course.total_distance
                rs.finished = True
                rs.finish_time = self.current_time

        self.current_time += 1

    def _decide_surges(
        self,
        positions: list[float],
        sorted_idx: list[int],
        gradients: list[float],
    ) -> None:
        """Trigger an energy-burst effort for riders facing a decisive moment.

        Reflex-based (not a full tactic model): a rider launches a surge to
        contest the finish, attack a climb to break away, or chase a leader.
        Updates each rider's surge_ticks in place.
        """
        from .formulas import (
            ATTACK_MIN_CLIMB,
            ATTACK_MIN_GRADIENT,
            CHASE_GAP_THRESHOLD,
            DRAFT_DISTANCE,
            SPRINT_DISTANCE,
            SPRINT_DURATION,
            SPRINT_MIN_SPRINT,
            SURGE_COOLDOWN,
            SURGE_DURATION,
            SURGE_MIN_ENERGY,
        )

        course_length = self.course.total_distance

        for i, rs in enumerate(self.rider_states):
            if rs.finished or rs.surge_ticks > 0 or rs.surge_cooldown > 0:
                continue
            if rs.energy < SURGE_MIN_ENERGY:
                continue

            gradient = gradients[i]
            remaining = course_length - positions[i]
            attrs = rs.rider.attributes

            surge = False
            duration = SURGE_DURATION

            # 1. Finish sprint — inside the last stretch, strong sprinters kick.
            if (
                remaining <= SPRINT_DISTANCE
                and attrs.sprint >= SPRINT_MIN_SPRINT
            ):
                surge = True
                duration = SPRINT_DURATION

            # 2. Attack a climb — a strong climber on a steep section tries to
            # break away.
            elif gradient >= ATTACK_MIN_GRADIENT and attrs.climb >= ATTACK_MIN_CLIMB:
                surge = True

            # 3. Chase a leader — close the draft to a clear break ahead.
            else:
                leader = self._drafting_leader(
                    i, positions, sorted_idx, gradient
                )
                front = self._front_position(positions)
                if leader is None and front > positions[i]:
                    gap = front - positions[i]
                    if gap > DRAFT_DISTANCE and gap <= CHASE_GAP_THRESHOLD:
                        surge = True

            if surge:
                rs.surge_ticks = duration
                rs.surge_cooldown = SURGE_COOLDOWN

    @staticmethod
    def _front_position(positions: list[float]) -> float:
        return max(positions) if positions else 0.0

    def _drafting_leader(
        self,
        idx: int,
        positions: list[float],
        sorted_idx: list[int],
        gradient: float,
    ) -> int | None:
        """Return the index of the nearest rider drafting ahead of `idx`.

        Returns None when no rider is within DRAFT_DISTANCE ahead (or the rider
        is not drafting due to the terrain).
        """
        from .formulas import DRAFT_DISTANCE, DRAFT_UPHILL_LIMIT

        pos = positions[idx]

        if gradient > DRAFT_UPHILL_LIMIT:
            return None

        # sorted_idx is front-to-back, so the first rider ahead within range
        # is the nearest wheel in front. A finished rider provides no shelter.
        for other in sorted_idx:
            if other == idx:
                continue
            if self.rider_states[other].finished:
                continue
            diff = positions[other] - pos
            if diff >= 0 and diff <= DRAFT_DISTANCE:
                return other
        return None

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
            if self.rider_states[other].finished:
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
    seed: int | None = None,
    verbose: bool = False,
) -> list[RiderState]:
    from .race_logger import RaceLogger

    if seed is not None:
        import random

        random.seed(seed)

    state = RaceState.create_initial_state(riders, course)
    logger = RaceLogger(log_path) if log_path else None

    import sys
    import time as _time

    total_distance = course.total_distance
    progress_interval = 500  # ticks between progress lines
    start_wall = _time.monotonic() if verbose else 0.0

    try:
        if logger:
            logger.log(state)
        while not state.is_finished():
            state.tick()
            if logger:
                logger.log(state)
            if verbose and state.current_time % progress_interval == 0:
                last_pos = min(rs.position for rs in state.rider_states)
                pct = last_pos / total_distance * 100
                elapsed = _time.monotonic() - start_wall
                print(
                    f"\r  {pct:5.1f}%  tick {state.current_time:>6d}  "
                    f"wall {elapsed:6.1f}s",
                    end="",
                    file=sys.stderr,
                    flush=True,
                )
    finally:
        if logger:
            logger.close()

    if verbose:
        elapsed = _time.monotonic() - start_wall
        print(
            f"\r  100.0%  tick {state.current_time:>6d}  "
            f"wall {elapsed:6.1f}s",
            file=sys.stderr,
            flush=True,
        )

    return state.get_results()
