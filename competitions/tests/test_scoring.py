from __future__ import annotations

from racing.models import RaceMarker

from competitions.scoring import (
    POINTS_BY_POSITION,
    PRIZE_BY_POSITION,
    SPRINT_POINTS_BY_WEIGHT,
    points_for,
    prize_for,
    sprint_points_for,
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


def test_every_weight_has_exactly_five_scoring_places():
    for weight, table in SPRINT_POINTS_BY_WEIGHT.items():
        assert set(table) == {1, 2, 3, 4, 5}, weight


def test_sprint_points_decline_down_the_order():
    for weight, table in SPRINT_POINTS_BY_WEIGHT.items():
        values = [table[p] for p in sorted(table)]
        assert values == sorted(values, reverse=True), weight


def test_heavier_weights_never_pay_less():
    for position in range(1, 6):
        minor = sprint_points_for("minor", position)
        standard = sprint_points_for("standard", position)
        major = sprint_points_for("major", position)
        assert minor <= standard <= major


def test_major_sprint_win_is_at_most_half_a_race_win():
    assert sprint_points_for("major", 1) <= points_for(1) / 2


def test_sprint_position_outside_table_scores_zero():
    assert sprint_points_for("standard", 6) == 0
    assert sprint_points_for("standard", 50) == 0


def test_sprint_table_keys_match_marker_weights():
    assert set(SPRINT_POINTS_BY_WEIGHT) == set(RaceMarker.Weight.values)
