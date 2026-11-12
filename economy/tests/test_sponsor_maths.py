from __future__ import annotations

from economy.sponsors import PROFILES, PROFILES_BY_KEY, offer_terms, payment_for


def test_steady_profile_pays_base_regardless_of_points():
    steady = PROFILES_BY_KEY["steady"]
    terms = offer_terms(steady, fanbase=10_000, credits_per_thousand_fans=500)

    for points, average in [(0, 5.0), (50, 5.0), (0, None)]:
        assert payment_for(
            weekly_base=terms["weekly_base"],
            floor_amount=terms["floor_amount"],
            ceiling_amount=terms["ceiling_amount"],
            sensitivity=terms["sensitivity"],
            points=points,
            average_points=average,
        ) == terms["weekly_base"]


def test_payment_rises_above_average_and_falls_below():
    balanced = PROFILES_BY_KEY["balanced"]
    terms = offer_terms(balanced, fanbase=10_000, credits_per_thousand_fans=500)

    above = payment_for(
        weekly_base=terms["weekly_base"], floor_amount=terms["floor_amount"],
        ceiling_amount=terms["ceiling_amount"], sensitivity=terms["sensitivity"],
        points=20, average_points=10.0,
    )
    below = payment_for(
        weekly_base=terms["weekly_base"], floor_amount=terms["floor_amount"],
        ceiling_amount=terms["ceiling_amount"], sensitivity=terms["sensitivity"],
        points=0, average_points=10.0,
    )

    assert above > terms["weekly_base"] > below


def test_payment_never_leaves_the_range():
    demanding = PROFILES_BY_KEY["demanding"]
    terms = offer_terms(demanding, fanbase=10_000, credits_per_thousand_fans=500)

    for points in [0, 1, 10, 100, 1000]:
        amount = payment_for(
            weekly_base=terms["weekly_base"], floor_amount=terms["floor_amount"],
            ceiling_amount=terms["ceiling_amount"], sensitivity=terms["sensitivity"],
            points=points, average_points=5.0,
        )
        assert terms["floor_amount"] <= amount <= terms["ceiling_amount"]


def test_no_history_pays_base():
    for profile in PROFILES:
        terms = offer_terms(profile, fanbase=10_000, credits_per_thousand_fans=500)
        amount = payment_for(
            weekly_base=terms["weekly_base"], floor_amount=terms["floor_amount"],
            ceiling_amount=terms["ceiling_amount"], sensitivity=terms["sensitivity"],
            points=25, average_points=None,
        )
        assert amount == terms["weekly_base"]


def test_zero_average_does_not_divide_by_zero():
    balanced = PROFILES_BY_KEY["balanced"]
    terms = offer_terms(balanced, fanbase=10_000, credits_per_thousand_fans=500)

    amount = payment_for(
        weekly_base=terms["weekly_base"], floor_amount=terms["floor_amount"],
        ceiling_amount=terms["ceiling_amount"], sensitivity=terms["sensitivity"],
        points=5, average_points=0.0,
    )

    assert terms["floor_amount"] <= amount <= terms["ceiling_amount"]


def test_offers_scale_with_fanbase():
    balanced = PROFILES_BY_KEY["balanced"]
    small = offer_terms(balanced, fanbase=5_000, credits_per_thousand_fans=500)
    big = offer_terms(balanced, fanbase=20_000, credits_per_thousand_fans=500)

    assert big["weekly_base"] > small["weekly_base"]
    assert big["floor_amount"] > small["floor_amount"]
    assert big["ceiling_amount"] > small["ceiling_amount"]


def test_round_offers_one_of_each_profile():
    assert {p.key for p in PROFILES} == {"steady", "balanced", "demanding"}
    assert len(PROFILES) == 3
