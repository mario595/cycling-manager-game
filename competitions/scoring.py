from __future__ import annotations

#: Points by finishing position, 1-indexed. Positions beyond this score
#: nothing. Frozen per race at award time — see
#: specs/race-points-and-standings.md.
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


#: How many crossing positions at a sprint marker score.
SPRINT_PLACES = 5

#: Sprint points by marker weight, then crossing position (1-indexed).
#: Positions beyond SPRINT_PLACES score nothing. Frozen per marker at award
#: time — see specs/sprint-points.md. Keys match RaceMarker.Weight.
SPRINT_POINTS_BY_WEIGHT: dict[str, dict[int, int]] = {
    "minor":    {1: 4,  2: 3, 3: 2, 4: 1, 5: 1},
    "standard": {1: 6,  2: 4, 3: 3, 4: 2, 5: 1},
    "major":    {1: 10, 2: 7, 3: 5, 4: 3, 5: 2},
}


def sprint_points_for(weight: str, position: int) -> int:
    """What a crossing position at a sprint of this weight is worth. Zero
    outside the table."""
    return SPRINT_POINTS_BY_WEIGHT.get(weight, {}).get(position, 0)
