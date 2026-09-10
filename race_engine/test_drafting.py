"""Tests for gap-decayed shelter and the pack-aware `pulling` flag.

The old model credited shelter purely by ordinal pack depth, so a rider two
wheels back on paper but far off the wheel ahead got the same credit as one
riding right on the wheel — not physically defensible. It also set `pulling`
from a standalone pairwise "is anyone within DRAFT_DISTANCE behind me" check
rather than real pack structure, so the true pace-setter could show
`pulling=False` if nobody happened to be glued to their back wheel that
tick. A separate `drafting` flag existed too, but shelter degree doesn't
compress into a meaningful boolean (nearly everyone in a pack gets *some*
shelter, just to varying degrees), so it was removed rather than fixed — see
DOMAIN.md's "Drafting & pack cohesion". These tests build synthetic packs
with known gaps and check both the real shelter effect and `pulling`.
"""

from __future__ import annotations

from race_engine.formulas import DRAFT_DISTANCE, PACK_COHESION_DISTANCE
from race_engine.models import Course, RaceState, Rider, RiderAttributes, Segment

# A uniform roster (equal riders) isolates the gap effect from attribute
# differences — any speed/shelter difference between riders in these tests
# comes from position/gap alone.
ATTRS = RiderAttributes(climb=50, sprint=50, flat=50, resistance=50, positioning=60)


def _make_state(n: int, positions: list[float]) -> RaceState:
    riders = [Rider(id=f"r{i}", name=f"R{i}", attributes=ATTRS) for i in range(n)]
    course = Course(segments=[Segment(length=500_000.0, gradient=0.0)])
    state = RaceState.create_initial_state(riders, course, wind=False)
    for rs, pos in zip(state.rider_states, positions):
        rs.position = pos
    return state


def test_tight_chain_pulling():
    """A tight chain has exactly one pulling rider: the front of the pack."""
    positions = [100_000.0 - 2.0 * i for i in range(6)]
    state = _make_state(6, positions)
    state.tick()

    pulling = [rs.pulling for rs in state.rider_states]
    assert pulling == [True, False, False, False, False, False]


def test_front_rider_pulling_even_with_distant_trailing_rider():
    """The front rider pulls even if nobody is within 3m directly behind —
    this was the bug: the old flag needed a close trailing wheel to show
    `pulling`, so the true pace-setter often showed pulling=False."""
    # front at 100000, next rider 13m back (still pack-coherent, well within
    # PACK_COHESION_DISTANCE), rest close together further back.
    positions = [100_000.0, 99_987.0, 99_984.0, 99_981.0]
    state = _make_state(4, positions)
    state.tick()

    assert state.rider_states[0].pulling is True


def test_mid_pack_rider_with_distant_neighbours_does_not_pull():
    """A mid-pack rider with no close trailing/leading wheel is still not
    `pulling`, even though they're fully pack-coherent — only depth 0 pulls."""
    # r1 sits 13m behind r0 and 13m ahead of r2 — pack-coherent (well under
    # PACK_COHESION_DISTANCE both ways) but not within DRAFT_DISTANCE of
    # either neighbour.
    positions = [100_000.0, 99_987.0, 99_974.0]
    state = _make_state(3, positions)
    state.tick()

    assert state.rider_states[1].pulling is False


def test_close_gap_grants_more_shelter_than_distant_gap():
    """Two riders at the same ordinal depth (2) get different real shelter
    depending on physical gap to the wheel ahead — the actual mechanic fix,
    not just the display flags. Compare stamina drain (a function of the
    sustainable/shelter-credited reference) between a tight and a loose
    chain of the same length, over many ticks so the (per-tick tiny) effect
    isn't swamped by speed jitter, with a fixed seed for determinism."""
    import random

    random.seed(1)
    tight = _make_state(3, [100_000.0, 99_997.0, 99_994.0])  # 3m gaps
    random.seed(1)
    loose = _make_state(3, [100_000.0, 99_970.0, 99_940.0])  # 30m gaps
    for _ in range(100):
        tight.tick()
        loose.tick()

    tight_last, loose_last = tight.rider_states[2], loose.rider_states[2]
    # Both start at stamina 100; less shelter -> more drain -> lower stamina
    # for the loosely-spaced rider at the same ordinal depth.
    assert loose_last.stamina < tight_last.stamina


def test_gap_factor_shape_via_effective_speed():
    """gap_factor should be 1.0 within DRAFT_DISTANCE and fall toward 0 near
    PACK_COHESION_DISTANCE — check monotonic decay by comparing cumulative
    stamina drain (a per-tick effect too small to read reliably after a
    single tick) over many ticks of a rider holding a fixed gap to the wheel
    ahead in a 3-rider chain (so the trailing rider is unambiguously at
    depth 2, never the pack front). A fixed seed removes jitter noise."""
    import random

    gaps = [DRAFT_DISTANCE, 15.0, 30.0, 45.0, PACK_COHESION_DISTANCE - 1.0]
    final_stamina = []
    for gap in gaps:
        random.seed(1)
        state = _make_state(3, [100_000.0, 99_998.0, 100_000.0 - 2.0 - gap])
        for _ in range(200):
            state.tick()
            # Hold the gap constant tick over tick so the shelter effect
            # compounds instead of the riders drifting apart/together.
            front = state.rider_states[0].position
            state.rider_states[1].position = front - 2.0
            state.rider_states[2].position = front - 2.0 - gap
        final_stamina.append(state.rider_states[2].stamina)

    # Monotonically non-increasing shelter (non-increasing final stamina) as
    # the gap widens — a larger gap should never leave MORE stamina than a
    # smaller one.
    for i in range(len(final_stamina) - 1):
        assert final_stamina[i] >= final_stamina[i + 1] - 1e-6, (
            f"gap {gaps[i]} left less stamina than gap {gaps[i+1]}"
        )
    # And the tightest gap should leave meaningfully more stamina than the
    # widest — not just a monotone-but-flat sequence.
    assert final_stamina[0] > final_stamina[-1] + 0.01
