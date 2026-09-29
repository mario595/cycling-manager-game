from __future__ import annotations

#: Points by finishing position, 1-indexed. Positions beyond this score
#: nothing. Frozen per race at award time — see
#: specs/race-points-and-standings.md. This is the table for a one-day race
#: and for each stage of a stage race — see STAGE_POINTS_BY_POSITION.
POINTS_BY_POSITION: dict[int, int] = {
    1: 20, 2: 15, 3: 12, 4: 10, 5: 8, 6: 6, 7: 4, 8: 3, 9: 2, 10: 1,
}


def points_for(position: int) -> int:
    """What a finishing position is worth. Zero outside the table."""
    return POINTS_BY_POSITION.get(position, 0)


#: Prize money by finishing position, 1-indexed. Positions beyond this pay
#: nothing. Frozen per race at award time by virtue of the append-only
#: ledger — see specs/prize-money-for-race-results.md.
PRIZE_BY_POSITION: dict[int, int] = {
    1: 20_000, 2: 15_000, 3: 12_000, 4: 10_000, 5: 8_000,
    6: 6_000,  7: 4_000,  8: 3_000,  9: 2_000, 10: 1_000,
}


def prize_for(position: int) -> int:
    """What a finishing position pays. Zero outside the table."""
    return PRIZE_BY_POSITION.get(position, 0)


#: Points for one stage of a stage race — roughly half POINTS_BY_POSITION,
#: so a team that only ever finishes mid-pack still earns something every
#: stage without a long tour paying out as if it were several classics.
#: See specs/stage-races.md, Decisions taken.
STAGE_POINTS_BY_POSITION: dict[int, int] = {
    1: 10, 2: 8, 3: 6, 4: 5, 5: 4, 6: 3, 7: 2, 8: 2, 9: 1, 10: 1,
}


def stage_points_for(position: int) -> int:
    """What a stage finishing position is worth. Zero outside the table."""
    return STAGE_POINTS_BY_POSITION.get(position, 0)


#: Points for a stage race's final general classification — double
#: POINTS_BY_POSITION, worth building a squad around. Awarded once, on top
#: of every stage's own points, when the last stage finishes.
GC_POINTS_BY_POSITION: dict[int, int] = {
    1: 40, 2: 30, 3: 24, 4: 20, 5: 16, 6: 12, 7: 8, 8: 6, 9: 4, 10: 2,
}


def gc_points_for(position: int) -> int:
    """What a GC finishing position is worth. Zero outside the table."""
    return GC_POINTS_BY_POSITION.get(position, 0)


#: Prize money for one stage of a stage race — the stage counterpart of
#: STAGE_POINTS_BY_POSITION, same reasoning.
STAGE_PRIZE_BY_POSITION: dict[int, int] = {
    1: 10_000, 2: 7_500, 3: 6_000, 4: 5_000, 5: 4_000,
    6: 3_000,  7: 2_000, 8: 1_500, 9: 1_000, 10: 500,
}


def stage_prize_for(position: int) -> int:
    """What a stage finishing position pays. Zero outside the table."""
    return STAGE_PRIZE_BY_POSITION.get(position, 0)


#: Prize money for a stage race's final general classification — double
#: PRIZE_BY_POSITION, the GC counterpart of GC_POINTS_BY_POSITION.
GC_PRIZE_BY_POSITION: dict[int, int] = {
    1: 40_000, 2: 30_000, 3: 24_000, 4: 20_000, 5: 16_000,
    6: 12_000, 7: 8_000,  8: 6_000,  9: 4_000,  10: 2_000,
}


def gc_prize_for(position: int) -> int:
    """What a GC finishing position pays. Zero outside the table."""
    return GC_PRIZE_BY_POSITION.get(position, 0)
