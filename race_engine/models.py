from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


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
    team_id: str | None = None  # defaults to own id (a team of one) in __post_init__
    role: str = "leader"  # "leader" or "support"

    def __post_init__(self) -> None:
        if self.team_id is None:
            self.team_id = self.id


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


class Terrain(str, Enum):
    """Terrain bucket for a course segment, derived from its gradient."""

    FLAT = "flat"
    MODERATE = "moderate"
    STEEP = "steep"


@dataclass
class SegmentProfile:
    """A course segment with its cumulative start distance and terrain bucket."""

    length: float  # meters
    gradient: float  # %
    start_distance: float  # meters from start where this segment begins
    terrain: Terrain


@dataclass
class CourseProfile:
    """Pre-computed, from-where-you-stand view of the course for tactics."""

    total_distance: float
    segments: list[SegmentProfile]

    def terrain_at(self, position: float) -> Terrain:
        return self._find_segment(position).terrain

    def remaining(self, position: float) -> float:
        return max(0.0, self.total_distance - position)

    def remaining_fraction(self, position: float) -> float:
        return self.remaining(position) / self.total_distance

    def steepest_ahead(self, position: float, distance: float) -> float:
        """Max gradient (%) within `distance` meters ahead of `position`."""
        horizon = position + distance
        worst = 0.0
        for s in self.segments:
            end = s.start_distance + s.length
            if end <= position:
                continue
            if s.start_distance > horizon:
                break
            worst = max(worst, s.gradient)
        return worst

    def _find_segment(self, position: float, lo: int = 0, hi: int | None = None) -> SegmentProfile:
        if hi is None:
            hi = len(self.segments) - 1
        while lo <= hi:
            mid = (lo + hi) // 2
            s = self.segments[mid]
            end = s.start_distance + s.length
            if position < s.start_distance:
                hi = mid - 1
            elif position >= end:
                lo = mid + 1
            else:
                return s
        return self.segments[-1]


@dataclass
class RiderState:
    rider: Rider
    speed: float = 0.0  # m/s
    position: float = 0.0  # meters from start
    energy: float = 100.0  # 0-100
    stamina: float = 100.0  # 0-100
    pulling: bool = False  # currently setting the pace at the front of a pack
    surging: bool = False  # currently in an energy-burst effort
    sprinting: bool = False  # current surge is a finish-sprint kick (sized by `sprint`)
    surge_ticks: int = 0  # remaining ticks of the current surge
    surge_cooldown: int = 0  # ticks before another surge may start
    finished: bool = False
    finish_time: int | None = None  # seconds


@dataclass
class RaceState:
    course: Course
    rider_states: list[RiderState] = field(default_factory=list)
    current_time: int = 0  # seconds
    profile: CourseProfile | None = None

    @classmethod
    def create_initial_state(
        cls, riders: list[Rider], course: Course
    ) -> RaceState:
        rider_states = [RiderState(rider=r) for r in riders]
        state = cls(course=course, rider_states=rider_states, current_time=0)
        state.profile = cls._compute_profile(course)
        return state

    @staticmethod
    def _compute_profile(course: Course) -> CourseProfile:
        from .formulas import TERRAIN_MODERATE_THRESHOLD, TERRAIN_STEEP_THRESHOLD

        segments: list[SegmentProfile] = []
        offset = 0.0
        for seg in course.segments:
            g = seg.gradient
            if g >= TERRAIN_STEEP_THRESHOLD:
                terrain = Terrain.STEEP
            elif g >= TERRAIN_MODERATE_THRESHOLD:
                terrain = Terrain.MODERATE
            else:
                terrain = Terrain.FLAT
            segments.append(
                SegmentProfile(
                    length=seg.length,
                    gradient=seg.gradient,
                    start_distance=offset,
                    terrain=terrain,
                )
            )
            offset += seg.length
        return CourseProfile(
            total_distance=course.total_distance, segments=segments
        )

    def tick(self) -> None:
        from .formulas import (
            DRAFT_DISTANCE,
            DRAFT_UPHILL_LIMIT,
            SPRINT_BOOST_MAX,
            SPRINT_BOOST_MIN,
            SURGE_ENERGY_COST,
            SURGE_SPEED_BOOST,
            _lerp,
            add_speed_jitter,
            apply_energy_burst_modifier,
            apply_stamina_cruise_modifier,
            compute_base_speed,
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

        deltas = [None] * len(self.rider_states)  # (speed, energy_delta, stamina, pulling)
        gradients = [0.0] * len(self.rider_states)
        own_speeds = [0.0] * len(self.rider_states)

        for i, rs in enumerate(self.rider_states):
            if rs.finished:
                continue

            segment = self._find_segment(rs.position)
            if segment is None:
                # Past the finish line.
                deltas[i] = (0.0, 0.0, 0.0, False)
                continue

            gradients[i] = segment.gradient
            # Natural cruise pace — base speed throttled by stamina (cracking),
            # before any energy/burst considerations.
            cruise = apply_stamina_cruise_modifier(
                compute_base_speed(rs.rider.attributes, segment.gradient), rs.stamina
            )
            own_speeds[i] = add_speed_jitter(cruise)

        # Decide this tick whether any rider starts an energy surge (attack a
        # climb, chase a gap, or launch the finish sprint). Terrain- and
        # phase-aware (uses pre-computed course profile).
        self._decide_actions(positions, sorted_idx, gradients)

        # Resolve pack cohesion: riders within PACK_COHESION_DISTANCE of each other on
        # draft-allowed terrain cohere into a peloton that rolls at a shared,
        # controlled sustainable tempo rather than each at their own maximal
        # pace. A rider whose own cruise falls below the tempo is DROPPED
        # (cannot stay sheltered), so a fatigued rider doesn't drag the pack.
        # Riders currently surging break from the pack and ride their own pace.
        #
        # Packs are connected components over (undirected) proximity within
        # PACK_COHESION_DISTANCE. Found via BFS to avoid cycle risk.
        from .formulas import (
            BREAK_CLEAR_DISTANCE,
            PACK_COHESION_DISTANCE,
            ROTATION_SHARE_LEADER,
            ROTATION_SHARE_SUPPORT,
            TEAMMATE_SHELTER_BONUS,
            compute_pack_tempo,
            draft_hold_multiplier,
        )

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
        pulling_flags = [False] * len(self.rider_states)
        pack_depth = [0.0] * len(self.rider_states)

        # A pack of a single rider rides alone at their own cruise.
        for pack in packs:
            if len(pack) < 2:
                continue
            member_speeds = [own_speeds[m] for m in pack]
            # The pack picks a tempo for its situation rather than always
            # riding a fixed fraction of its strongest rider's ceiling: it
            # rolls on an early flat road, and only goes full gas in the finale
            # or when someone is clear up the road and worth chasing.
            front_member = max(pack, key=lambda m: positions[m])
            pack_front = positions[front_member]
            # Tier A3: a pack member ignores a break made up solely of their
            # own teammates when deciding whether there's something worth
            # chasing — bringing back your own rider helps nobody. Each
            # member's own team decides whether *they* see a chaseable
            # break; the pack tempo then reacts to the fraction of the pack
            # still willing, not an all-or-nothing pack-wide bool, so one
            # team with a rider away doesn't single-handedly call off the
            # chase for everyone else.
            clear_ahead = [
                o
                for o, other in enumerate(self.rider_states)
                if not other.finished and positions[o] - pack_front > BREAK_CLEAR_DISTANCE
            ]
            willing = 0
            for m in pack:
                my_team = self.rider_states[m].rider.team_id
                if any(self.rider_states[o].rider.team_id != my_team for o in clear_ahead):
                    willing += 1
            chase_willingness = willing / len(pack) if clear_ahead else 0.0
            pace = compute_pack_tempo(
                member_speeds,
                self.profile.remaining_fraction(pack_front),
                self.profile.terrain_at(pack_front),
                chase_willingness,
                gradients[front_member],
            )
            # Shelter is credited to both the tempo-hold test and the depth
            # bookkeeping, so a weaker rider sheltering deep in the group (e.g.
            # a climber in the bunch on the flat) can hold the tempo even if
            # their SOLO cruise is below it. An exposed rider (depth 0) gets no
            # credit and is dropped if their own cruise can't hold pace.
            by_pos = sorted(pack, key=lambda m: positions[m], reverse=True)
            depth_of: dict[int, int] = {}
            for d, m in enumerate(by_pos):
                depth_of[m] = d  # 0 = front/pulling, 1 = first wheel, ...
            # Gap to the wheel immediately ahead in the chain, for depth 0
            # (front) this is irrelevant — draft_hold_multiplier special-cases
            # depth < 1 to no credit regardless.
            gap_ahead: dict[int, float] = {}
            wheel_ahead: dict[int, int | None] = {}
            for d, m in enumerate(by_pos):
                wheel_ahead[m] = by_pos[d - 1] if d >= 1 else None
                gap_ahead[m] = positions[wheel_ahead[m]] - positions[m] if d >= 1 else 0.0
            # Real drafting benefit falls off sharply with physical distance —
            # a rider two wheels back on paper but 13 m off the wheel ahead
            # isn't meaningfully sheltered. gap_factor is 1.0 at DRAFT_DISTANCE
            # and decays linearly to 0 by PACK_COHESION_DISTANCE (the edge of
            # the pack itself).
            gap_factor_of = {
                m: max(
                    0.0,
                    min(
                        1.0,
                        1.0
                        - max(0.0, gap_ahead[m] - DRAFT_DISTANCE)
                        / (PACK_COHESION_DISTANCE - DRAFT_DISTANCE),
                    ),
                )
                for m in pack
            }
            # Teammate shelter priority (Tier A1): a rider sitting on a
            # teammate's wheel gets a bonus on top of the gap-decayed value —
            # real teams hand each other wheels deliberately, strangers just
            # happen to be near each other. Scaled by the same gap_factor so
            # it still requires being physically close enough to shelter at
            # all (a teammate 50m up the road grants no bonus).
            teammate_bonus_of = {
                m: (
                    TEAMMATE_SHELTER_BONUS * gap_factor_of[m]
                    if wheel_ahead[m] is not None
                    and self.rider_states[wheel_ahead[m]].rider.team_id
                    == self.rider_states[m].rider.team_id
                    else 0.0
                )
                for m in pack
            }
            # The drop test and fatigue reference use rotation-averaged depth
            # (real bunches rotate — nobody is on the front the whole race),
            # scaled by the same gap_factor so the rotation floor still
            # protects against one noisy tick's ordinal position without
            # overriding a genuinely large, sustained physical gap — that
            # combination is what keeps this from reintroducing the coin-flip
            # drops rotation-averaging was built to remove.
            #
            # Role-scaled (Tier A2): a support rider's floor is lower (they
            # really do take more than their share of front-line time for
            # the team) and a leader's is higher (teammates hand them more
            # shelter than their instantaneous position alone would credit).
            # This biases the rotation *average* the fatigue formulas see —
            # a leader physically at the front this tick still pulls (depth
            # 0, `pulling=True` below); only the drop-test/fatigue reference
            # is protected.
            eff_depth_of = {}
            for m, d in depth_of.items():
                role = self.rider_states[m].rider.role
                share = ROTATION_SHARE_LEADER if role == "leader" else ROTATION_SHARE_SUPPORT
                rotation_floor = share * (len(pack) - 1)
                eff_depth_of[m] = (
                    max(float(d) * gap_factor_of[m], rotation_floor * gap_factor_of[m])
                    + teammate_bonus_of[m]
                )
            coherent = [
                m
                for m in pack
                if own_speeds[m]
                * draft_hold_multiplier(
                    self.rider_states[m].rider.attributes.positioning,
                    eff_depth_of[m],
                    gradients[m],
                )
                >= pace
            ]
            for m in coherent:
                # Pulling is exactly the rider setting the pace (depth 0) in
                # a real multi-member pack — everyone else in the pack is
                # sheltering to some degree (see gap_factor above), which
                # doesn't compress into a meaningful boolean, so there is no
                # separate "drafting" flag: assume the front rider is doing
                # the work and everyone else is benefiting, unevenly.
                if depth_of[m] == 0:
                    pulling_flags[m] = True
                effective_speeds[m] = pace
                pack_depth[m] = eff_depth_of[m]

        for i, rs in enumerate(self.rider_states):
            if rs.finished or deltas[i] is not None:
                continue

            pulling = pulling_flags[i]
            # The speed this rider can hold for free in the position they are
            # actually riding: their own cruise when exposed or alone, more
            # when sheltered. Same reference the cohesion drop test uses, so
            # holding the tempo the engine says they can hold is not charged —
            # by either fatigue meter.
            sustainable = own_speeds[i] * draft_hold_multiplier(
                rs.rider.attributes.positioning, pack_depth[i], gradients[i]
            )

            if rs.surge_ticks > 0:
                # Active surge: ride boosted own speed, burn extra energy.
                # A finish-sprint kick is sized by the `sprint` attribute
                # rather than the flat SURGE_SPEED_BOOST every other surge
                # uses — see `_decide_actions` rule 1.
                if rs.sprinting:
                    t_sprint = (rs.rider.attributes.sprint - 1) / 99.0
                    boost = _lerp(SPRINT_BOOST_MIN, SPRINT_BOOST_MAX, t_sprint)
                else:
                    boost = SURGE_SPEED_BOOST
                surge_speed = own_speeds[i] * (1.0 + boost)
                effective = add_speed_jitter(
                    apply_energy_burst_modifier(surge_speed, rs.energy)
                )
                energy_drain = (
                    compute_energy_drain(effective, sustainable)
                    + SURGE_ENERGY_COST
                )
                rs.surge_ticks -= 1
            else:
                # Adopted group pace, with the rider's energy-burst throttle.
                group_pace = effective_speeds[i]
                effective = add_speed_jitter(
                    apply_energy_burst_modifier(group_pace, rs.energy)
                )
                energy_drain = compute_energy_drain(effective, sustainable)

            stamina_drain = compute_stamina_drain(
                gradients[i], effective, sustainable,
                rs.rider.attributes.resistance,
            )

            if rs.surge_cooldown > 0:
                rs.surge_cooldown -= 1

            deltas[i] = (effective, energy_drain, stamina_drain, pulling)

        # Phase 2: apply all deltas consistently.
        for i, rs in enumerate(self.rider_states):
            if rs.finished:
                continue

            delta = deltas[i]
            if delta is None:
                continue

            speed, energy_drain, stamina_drain, pulling = delta
            rs.speed = speed
            rs.pulling = pulling
            rs.surging = rs.surge_ticks > 0
            if not rs.surging:
                rs.sprinting = False

            rs.position += speed  # 1 tick = 1 second

            rs.energy = max(0.0, min(100.0, rs.energy - energy_drain))
            rs.stamina = max(0.0, min(100.0, rs.stamina - stamina_drain))

            if rs.position >= self.course.total_distance:
                rs.position = self.course.total_distance
                rs.finished = True
                rs.finish_time = self.current_time

        self.current_time += 1

    def _decide_actions(
        self,
        positions: list[float],
        sorted_idx: list[int],
        gradients: list[float],
    ) -> None:
        """Decide the energy-burst effort each rider launches this tick.

        Terrain- and phase-aware rule-set layered over emerging group behavior.
        Riders evaluate their situation (remaining distance, terrain ahead,
        their own energy budget) before choosing to surge, so they only make
        efforts they can plausibly sustain — mimicking how a real pro manages
        their race. First matching rule wins:
          1. Finish sprint — inside the final kilometer, everyone kicks; the
             `sprint` attribute sizes the boost (see `sprinting` handling in
             `tick`), it no longer gates eligibility.
          2. Climb attack — in the finale/transition, on a steep gradient.
          3. Bridge to a break — a genuinely clear move (not just "no wheel
             within 3m"), only from the front of one's own group.
        Otherwise the rider rides the pack tempo.
        """
        from .formulas import (
            ATTACK_MIN_CLIMB,
            ATTACK_PHASE_THRESHOLD,
            BREAK_CLEAR_DISTANCE,
            BRIDGE_GAP_MAX,
            BRIDGE_MAX_DEPTH,
            CHASE_MIN_ENERGY,
            SPRINT_BOOST_MAX,
            SPRINT_BOOST_MIN,
            SPRINT_DISTANCE,
            SPRINT_DURATION,
            SPRINT_MIN_ENERGY,
            SURGE_COOLDOWN,
            SURGE_DURATION,
            SURGE_MIN_ENERGY,
            _lerp,
        )

        profile = self.profile

        for i, rs in enumerate(self.rider_states):
            if rs.finished or rs.surge_ticks > 0 or rs.surge_cooldown > 0:
                continue

            pos = positions[i]
            gradient = gradients[i]
            attrs = rs.rider.attributes
            remaining_frac = profile.remaining_fraction(pos)

            surge = False
            sprinting = False
            duration = SURGE_DURATION

            # 1. Finish sprint — inside the last stretch, everyone kicks; the
            # `sprint` attribute sizes the boost (applied in `tick`), not
            # whether the kick happens at all.
            if pos >= self.course.total_distance - SPRINT_DISTANCE:
                if rs.energy >= SPRINT_MIN_ENERGY:
                    surge = True
                    sprinting = True
                    duration = SPRINT_DURATION
            # 2. Attack a climb — in the finale/transition, on a steep gradient,
            # only within a viable distance of the finish.
            elif (
                remaining_frac < ATTACK_PHASE_THRESHOLD
                and profile.terrain_at(pos) is Terrain.STEEP
                and attrs.climb >= ATTACK_MIN_CLIMB
            ):
                if rs.energy >= SURGE_MIN_ENERGY:
                    surge = True

            # 3. Bridge to a break — only riders at the front of their own
            # group (depth <= BRIDGE_MAX_DEPTH) consider it, and only when
            # someone is genuinely clear (break_ahead, the same test pack
            # tempo uses — not just "no wheel within 3m", which every rider
            # in a strung-out bunch satisfies every tick). A team leader sits
            # in and saves themself for the finale instead of spending energy
            # on a speculative early move — that's what support riders are
            # for (Tier A4, TEAM_TACTICS_PLAN.md).
            elif rs.rider.role != "leader":
                group_front, depth = self._group_front_and_depth(
                    i, positions, sorted_idx, gradients
                )
                if depth <= BRIDGE_MAX_DEPTH:
                    leader_pos = self._nearest_clear_leader(
                        i, group_front, positions
                    )
                    if leader_pos is not None:
                        gap = leader_pos - pos
                        if gap <= BRIDGE_GAP_MAX:
                            if rs.energy >= CHASE_MIN_ENERGY and self._can_chase(
                                i, positions, sorted_idx, gradient
                            ):
                                surge = True

            if surge:
                rs.surge_ticks = duration
                rs.surge_cooldown = SURGE_COOLDOWN
                rs.sprinting = sprinting

    def _can_chase(
        self,
        idx: int,
        positions: list[float],
        sorted_idx: list[int],
        gradient: float,
    ) -> bool:
        """True if chasing the leader is plausible for this rider.

        On steep terrain a chase is only worthwhile if the leader is no more
        than a threshold stronger a climber than the chaser — otherwise the
        gap will not close and the effort is wasted. On flat/descending
        terrain a chase is always plausible (the chaser can draft/bridge).
        """
        from .formulas import DRAFT_UPHILL_LIMIT, CHASE_MIN_CLIMB_ADVANTAGE

        if gradient <= DRAFT_UPHILL_LIMIT:
            return True
        leader = None
        for other in sorted_idx:
            if other == idx or self.rider_states[other].finished:
                continue
            if positions[other] > positions[idx]:
                leader = other
                break
        if leader is None:
            return True
        my_climb = self.rider_states[idx].rider.attributes.climb
        leader_climb = self.rider_states[leader].rider.attributes.climb
        # CHASE_MIN_CLIMB_ADVANTAGE is negative; -advantage is the max
        # lead we will accept (i.e. don't chase a leader clearly stronger).
        return (leader_climb - my_climb) <= -CHASE_MIN_CLIMB_ADVANTAGE

    def _group_front_and_depth(
        self,
        idx: int,
        positions: list[float],
        sorted_idx: list[int],
        gradients: list[float],
    ) -> tuple[float, int]:
        """The front-most position of `idx`'s own contiguous group, and depth.

        Walks the chain of riders within PACK_COHESION_DISTANCE of each other
        ahead of `idx` (same coherence distance the pack-cohesion BFS uses),
        so a rider deep in a strung-out bunch sees their own group's front —
        not the absolute race leader — as the reference for "is a break
        ahead". Depth is how many riders are in that chain ahead of `idx`.
        Finished riders and gradients above DRAFT_UPHILL_LIMIT break the
        chain (no cohesion there), same as pack cohesion in `tick`.
        """
        from .formulas import DRAFT_UPHILL_LIMIT, PACK_COHESION_DISTANCE

        pos = positions[idx]
        if gradients[idx] > DRAFT_UPHILL_LIMIT:
            return pos, 0

        # sorted_idx is front-to-back; walk it back-to-front starting from
        # idx's own position, so each step considers the nearest rider ahead
        # of the chain built so far — this is the chain reachable from idx by
        # PACK_COHESION_DISTANCE hops toward the front, not the whole field.
        front = pos
        depth = 0
        cursor = pos
        for other in reversed(sorted_idx):
            if self.rider_states[other].finished:
                continue
            other_pos = positions[other]
            if other_pos <= cursor:
                continue
            if other_pos - cursor <= PACK_COHESION_DISTANCE:
                front = other_pos
                cursor = other_pos
                depth += 1
            else:
                break
        return front, depth

    def _nearest_clear_leader(
        self, idx: int, group_front: float, positions: list[float]
    ) -> float | None:
        """Nearest rider genuinely clear of `idx`'s group (a real break).

        "Clear" mirrors the pack-tempo chase test: more than
        BREAK_CLEAR_DISTANCE ahead of the group's front rider — not merely
        outside DRAFT_DISTANCE, which every rider in a strung-out bunch
        satisfies every tick. Excludes `idx`'s own teammates (Tier A3):
        bridging to your own leader/teammate isn't chasing a break, it's
        just riding up to them, so it shouldn't be evaluated (or energy-
        gated) as a chase. Returns the nearest qualifying rider's position,
        or None if nobody clear and unrelated is up the road.
        """
        from .formulas import BREAK_CLEAR_DISTANCE

        my_team = self.rider_states[idx].rider.team_id
        threshold = group_front + BREAK_CLEAR_DISTANCE
        clear_ahead = [
            positions[o]
            for o, rs in enumerate(self.rider_states)
            if positions[o] > threshold and rs.rider.team_id != my_team
        ]
        if not clear_ahead:
            return None
        return min(clear_ahead)

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
    team_codes: dict[str, dict[str, str]] | None = None,
) -> list[RiderState]:
    from .race_logger import RaceLogger

    if seed is not None:
        import random

        random.seed(seed)

    state = RaceState.create_initial_state(riders, course)
    logger = RaceLogger(log_path, team_codes=team_codes) if log_path else None

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
