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
