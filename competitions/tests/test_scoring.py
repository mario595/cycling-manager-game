from __future__ import annotations

from competitions.scoring import (
    GC_POINTS_BY_POSITION,
    GC_PRIZE_BY_POSITION,
    POINTS_BY_POSITION,
    PRIZE_BY_POSITION,
    STAGE_POINTS_BY_POSITION,
    STAGE_PRIZE_BY_POSITION,
    gc_points_for,
    gc_prize_for,
    points_for,
    prize_for,
    stage_points_for,
    stage_prize_for,
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


def test_all_tables_cover_same_positions():
    tables = [
        POINTS_BY_POSITION, PRIZE_BY_POSITION,
        STAGE_POINTS_BY_POSITION, STAGE_PRIZE_BY_POSITION,
        GC_POINTS_BY_POSITION, GC_PRIZE_BY_POSITION,
    ]
    for table in tables:
        assert set(table) == {1, 2, 3, 4, 5, 6, 7, 8, 9, 10}


def test_stage_points_by_position():
    assert stage_points_for(1) == 10
    assert stage_points_for(10) == 1
    assert stage_points_for(11) == 0


def test_gc_points_by_position():
    assert gc_points_for(1) == 40
    assert gc_points_for(10) == 2
    assert gc_points_for(11) == 0


def test_stage_prize_by_position():
    assert stage_prize_for(1) == 10_000
    assert stage_prize_for(10) == 500
    assert stage_prize_for(11) == 0


def test_gc_prize_by_position():
    assert gc_prize_for(1) == 40_000
    assert gc_prize_for(10) == 2_000
    assert gc_prize_for(11) == 0


def test_gc_tables_pay_double_the_one_day_table():
    for position in GC_POINTS_BY_POSITION:
        assert GC_POINTS_BY_POSITION[position] == 2 * POINTS_BY_POSITION[position]
    for position in GC_PRIZE_BY_POSITION:
        assert GC_PRIZE_BY_POSITION[position] == 2 * PRIZE_BY_POSITION[position]
