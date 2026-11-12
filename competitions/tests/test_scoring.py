from __future__ import annotations

from racing.models import RaceMarker

from competitions.scoring import (
    GC_POINTS_BY_POSITION,
    GC_PRIZE_BY_POSITION,
    MOUNTAIN_POINTS_BY_CATEGORY,
    POINTS_BY_POSITION,
    PRIZE_BY_POSITION,
    SPRINT_POINTS_BY_WEIGHT,
    STAGE_POINTS_BY_POSITION,
    STAGE_PRIZE_BY_POSITION,
    gc_points_for,
    gc_prize_for,
    mountain_points_for,
    points_for,
    prize_for,
    sprint_points_for,
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
    assert prize_for(1) == 22_000
    assert prize_for(2) == 16_500
    assert prize_for(3) == 13_200
    assert prize_for(4) == 11_000
    assert prize_for(5) == 8_800
    assert prize_for(6) == 6_600
    assert prize_for(7) == 4_400
    assert prize_for(8) == 3_300
    assert prize_for(9) == 2_200
    assert prize_for(10) == 1_100


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
    assert stage_prize_for(1) == 11_000
    assert stage_prize_for(10) == 550
    assert stage_prize_for(11) == 0


def test_gc_prize_by_position():
    assert gc_prize_for(1) == 44_000
    assert gc_prize_for(10) == 2_200
    assert gc_prize_for(11) == 0


def test_gc_tables_pay_double_the_one_day_table():
    for position in GC_POINTS_BY_POSITION:
        assert GC_POINTS_BY_POSITION[position] == 2 * POINTS_BY_POSITION[position]
    for position in GC_PRIZE_BY_POSITION:
        assert GC_PRIZE_BY_POSITION[position] == 2 * PRIZE_BY_POSITION[position]


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


def test_every_category_has_exactly_five_scoring_places():
    for category, table in MOUNTAIN_POINTS_BY_CATEGORY.items():
        assert set(table) == {1, 2, 3, 4, 5}, category


def test_mountain_points_decline_down_the_order():
    for category, table in MOUNTAIN_POINTS_BY_CATEGORY.items():
        values = [table[p] for p in sorted(table)]
        assert values == sorted(values, reverse=True), category


def test_harder_categories_never_pay_less():
    for position in range(1, 6):
        cat3 = mountain_points_for("cat3", position)
        cat2 = mountain_points_for("cat2", position)
        cat1 = mountain_points_for("cat1", position)
        hc = mountain_points_for("hc", position)
        assert cat3 <= cat2 <= cat1 <= hc


def test_hc_win_is_at_most_half_a_race_win():
    assert mountain_points_for("hc", 1) <= points_for(1) / 2


def test_hc_win_equals_major_sprint_win():
    """Deliberate parity, so neither specialist is favoured before the
    retune the spec defers. Changing this belongs to the retune ticket."""
    assert mountain_points_for("hc", 1) == sprint_points_for("major", 1)


def test_mountain_position_outside_table_scores_zero():
    assert mountain_points_for("cat2", 6) == 0
    assert mountain_points_for("cat2", 50) == 0


def test_mountain_table_keys_match_marker_categories():
    assert set(MOUNTAIN_POINTS_BY_CATEGORY) == set(RaceMarker.Category.values)
