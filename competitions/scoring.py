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
