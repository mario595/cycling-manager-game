"""The AI market's decision helpers, then its orchestrators.

The helpers are pure — rider lists in, answer out — so they are tested with
unsaved `Rider` instances and no database. The orchestrators are
database-backed and are tested by what ends up on an auction.
"""

from __future__ import annotations

from riders.models import Rider
from world.ai_market import (
    AI_MIN_ROSTER,
    buyer_rank,
    headroom,
    pick_listing,
    wants_rider,
)


def _rider(
    name: str, level: int = 50, *, age: int = 27, speciality: str = Rider.Speciality.ROULEUR,
) -> Rider:
    """An unsaved rider whose strength is `level` across all five engine
    attributes — enough to rank riders against each other without a query."""
    return Rider(
        name=name,
        speciality=speciality,
        age=age,
        climb=level, sprint=level, flat=level, resistance=level, positioning=level,
    )


def _roster_of(size: int, *, speciality: str = Rider.Speciality.DOMESTIQUE) -> list[Rider]:
    return [_rider(f"Rider {i}", 50, speciality=speciality) for i in range(size)]


def test_wants_a_rider_stronger_than_its_second_best_of_that_speciality():
    roster = _roster_of(AI_MIN_ROSTER) + [
        _rider("Second Best", 60),
        _rider("Best", 65),
    ]
    rider = _rider("For Sale", 70)

    assert wants_rider(roster, rider, pending_wins=0) is True


def test_does_not_want_a_rider_weaker_than_two_of_that_speciality():
    roster = _roster_of(AI_MIN_ROSTER) + [
        _rider("Best", 70),
        _rider("Second Best", 65),
    ]
    rider = _rider("For Sale", 60)

    assert wants_rider(roster, rider, pending_wins=0) is False


def test_thin_roster_wants_any_rider():
    roster = [
        _rider("Best", 70),
        _rider("Second Best", 65),
        *_roster_of(AI_MIN_ROSTER - 3, speciality=Rider.Speciality.DOMESTIQUE),
    ]
    rider = _rider("For Sale", 60)

    assert wants_rider(roster, rider, pending_wins=0) is True


def test_does_not_want_an_ageing_rider():
    rider = _rider("For Sale", 60, age=33)

    assert wants_rider(_roster_of(AI_MIN_ROSTER - 1), rider, pending_wins=0) is False


def test_does_not_want_when_roster_plus_pending_reaches_max():
    roster = _roster_of(14, speciality=Rider.Speciality.DOMESTIQUE)
    rider = _rider("For Sale", 60)

    assert wants_rider(roster, rider, pending_wins=1) is False


def test_buyer_rank_prefers_thin_then_fewest_of_speciality_then_pk():
    rider = _rider("For Sale", 60)
    thin = _roster_of(AI_MIN_ROSTER - 1, speciality=Rider.Speciality.ROULEUR)
    full = _roster_of(AI_MIN_ROSTER)
    few_specialists = full + [_rider("Sprinter", 50, speciality=Rider.Speciality.SPRINTER)]
    many_specialists = full + [_rider("Rouleur", 50), _rider("Rouleur", 50)]

    assert buyer_rank(thin, rider, 9) == (0, AI_MIN_ROSTER - 1, 9)
    assert buyer_rank(few_specialists, rider, 9) < buyer_rank(many_specialists, rider, 4)
    assert buyer_rank(few_specialists, rider, 4) < buyer_rank(few_specialists, rider, 7)


def test_pick_listing_surplus_lists_weakest():
    weak = _rider("Weak", 40)
    strong = _rider("Strong", 60)
    roster = [weak, strong, *_roster_of(11)]

    assert pick_listing(roster, [strong, weak]) is weak


def test_pick_listing_lists_oldest_ageing_non_top_rider():
    best = _rider("Best", 80, age=45)
    second = _rider("Second Best", 70, age=42)
    middle = _rider("Middle", 50, age=38)
    weakest = _rider("Weakest", 45, age=35)
    roster = [best, second, middle, weakest, *_roster_of(8)]

    assert pick_listing(roster, [best, second, middle, weakest]) is middle


def test_pick_listing_never_lists_a_top_rider_of_their_speciality():
    best = _rider("Best", 80, age=44)
    second = _rider("Second Best", 60, age=40)
    reserve = _rider("Reserve", 45, age=33)
    roster = [best, second, reserve, *_roster_of(9)]

    assert pick_listing(roster, [best, second, reserve]) is reserve


def test_pick_listing_returns_none_when_nothing_qualifies():
    roster = [_rider(f"Rider {i}", 50) for i in range(12)]

    assert pick_listing(roster, [_rider("Young", 60, age=30)]) is None


def test_headroom_keeps_the_cushion_and_subtracts_commitments():
    assert headroom(100_000, 0) == 50_000
    assert headroom(100_000, 20_000) == 30_000


def test_headroom_is_zero_for_negative_balance():
    assert headroom(-100, 0) == 0
    assert headroom(0, 0) == 0
    assert headroom(1_000, 5_000) == 0
