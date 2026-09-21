from __future__ import annotations

from competitions.scoring import (
    POINTS_BY_POSITION,
    PRIZE_BY_POSITION,
    points_for,
    prize_for,
)


def test_points_by_position():
    assert points_for(1) == 20
    assert points_for(2) == 15
    assert points_for(3) == 12
    assert points_for(4) == 10
    assert points_for(5) == 8
    assert points_for(6) == 6
    assert points_for(7) == 4
    assert points_for(8) == 3
    assert points_for(9) == 2
    assert points_for(10) == 1


def test_position_outside_table_scores_zero():
    assert points_for(11) == 0
    assert points_for(50) == 0


def test_table_has_exactly_ten_scoring_positions():
    assert len(POINTS_BY_POSITION) == 10


def test_prize_by_position():
    assert prize_for(1) == 20_000
    assert prize_for(2) == 15_000
    assert prize_for(3) == 12_000
    assert prize_for(4) == 10_000
    assert prize_for(5) == 8_000
    assert prize_for(6) == 6_000
    assert prize_for(7) == 4_000
    assert prize_for(8) == 3_000
    assert prize_for(9) == 2_000
    assert prize_for(10) == 1_000


def test_position_outside_table_pays_nothing():
    assert prize_for(11) == 0
    assert prize_for(50) == 0


def test_prize_table_matches_points_table_positions():
    assert set(PRIZE_BY_POSITION) == set(POINTS_BY_POSITION)
    assert set(PRIZE_BY_POSITION) == {1, 2, 3, 4, 5, 6, 7, 8, 9, 10}
