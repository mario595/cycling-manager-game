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
#: See specs/archive/stage-races.md, Decisions taken.
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


#: How many crossing positions at a sprint marker score.
SPRINT_PLACES = 5

#: Sprint points by marker weight, then crossing position (1-indexed).
#: Positions beyond SPRINT_PLACES score nothing. Frozen per marker at award
#: time — see specs/archive/sprint-points.md. Keys match RaceMarker.Weight.
SPRINT_POINTS_BY_WEIGHT: dict[str, dict[int, int]] = {
    "minor":    {1: 4,  2: 3, 3: 2, 4: 1, 5: 1},
    "standard": {1: 6,  2: 4, 3: 3, 4: 2, 5: 1},
    "major":    {1: 10, 2: 7, 3: 5, 4: 3, 5: 2},
}


def sprint_points_for(weight: str, position: int) -> int:
    """What a crossing position at a sprint of this weight is worth. Zero
    outside the table."""
    return SPRINT_POINTS_BY_WEIGHT.get(weight, {}).get(position, 0)
