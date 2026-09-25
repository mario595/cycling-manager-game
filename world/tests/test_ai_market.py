"""The AI market's decision helpers, then its orchestrators.

The helpers are pure — rider lists in, answer out — so they are tested with
unsaved `Rider` instances and no database. The orchestrators are
database-backed and are tested by what ends up on an auction.
"""

from __future__ import annotations

from datetime import timedelta

from accounts.models import User
from economy.models import STARTING_BALANCE, LedgerEntry
from economy.services import ensure_opening_balance
from riders.models import Rider
from schedule.models import Season, Week
from teams.models import Team
from transfers.models import Auction, Bid
from transfers.pricing import reserve_price_for
from transfers.services import list_for_auction, place_bid, withdraw_bids
from world.ai_market import (
    AI_LISTING_EVERY_WEEKS,
    AI_MIN_ROSTER,
    buyer_rank,
    headroom,
    list_ai_riders,
    pick_listing,
    place_ai_bids,
    wants_rider,
)
from world.clocks import MockClock
from world.services import get_clock, now


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


def _saved_rider(
    name: str, team: Team = None, *, level: int = 50, age: int = 27,
    speciality: str = Rider.Speciality.ROULEUR,
) -> Rider:
    return Rider.objects.create(
        name=name, team=team, speciality=speciality, age=age,
        climb=level, sprint=level, flat=level, resistance=level, positioning=level,
    )


def _ai_team(name: str, code: str, *, balance: int = STARTING_BALANCE) -> Team:
    team = Team.objects.create(name=name, code=code)
    ensure_opening_balance(team, at=now())
    if balance != STARTING_BALANCE:
        LedgerEntry.objects.create(
            team=team,
            kind=LedgerEntry.Kind.WAGES,
            amount=balance - STARTING_BALANCE,
            occurred_at=now(),
            description="Weekly wages",
        )
    return team


def _ai_roster(team: Team, size: int = AI_MIN_ROSTER + 2) -> list[Rider]:
    """A full, unremarkable roster of domestiques, so the AI team's want for a
    listed rouleur comes down to the need rule rather than thinness."""
    return [
        _saved_rider(f"{team.code} Domestique {i}", team, level=40, speciality=Rider.Speciality.DOMESTIQUE)
        for i in range(size)
    ]


def _seller(code: str = "SEL") -> Team:
    manager = User.objects.create_user(email=f"{code.lower()}@example.com", password="s0meth1ng-good")
    return Team.objects.create(name=f"{code} Human Team", code=code, manager=manager)


def test_ai_bids_reserve_on_a_needed_human_listing(db):
    seller = _seller()
    listed = _saved_rider("For Sale", seller, level=60)
    auction = list_for_auction(seller, listed.pk, at=now())
    ai = _ai_team("AI Alpha", "AIA")
    _ai_roster(ai)

    placed, error = place_ai_bids(at=now())

    bid = auction.bids.get()
    assert (placed, error) == (1, "")
    assert bid.bidder_team_id == ai.pk
    assert bid.amount == auction.reserve_price


def test_ai_ignores_listing_by_unmanaged_team(db):
    seller = _ai_team("AI Seller", "AIS")
    listed = _saved_rider("For Sale", seller, level=60)
    list_for_auction(seller, listed.pk, at=now())
    buyer = _ai_team("AI Buyer", "AIB")
    _ai_roster(buyer)

    placed, error = place_ai_bids(at=now())

    assert (placed, error) == (0, "")
    assert Bid.objects.exists() is False


def test_ai_ignores_auction_that_already_has_a_live_bid(db):
    seller = _seller()
    listed = _saved_rider("For Sale", seller, level=60)
    auction = list_for_auction(seller, listed.pk, at=now())
    human = _seller("HUM")
    place_bid(auction.pk, human, auction.reserve_price, at=now())
    ai = _ai_team("AI Alpha", "AIA")
    _ai_roster(ai)

    placed, error = place_ai_bids(at=now())

    assert (placed, error) == (0, "")
    assert auction.bids.live().count() == 1


def test_ai_bids_on_auction_whose_only_bid_was_withdrawn(db):
    seller = _seller()
    listed = _saved_rider("For Sale", seller, level=60)
    auction = list_for_auction(seller, listed.pk, at=now())
    claimed = _seller("CLM")
    place_bid(auction.pk, claimed, auction.reserve_price, at=now())
    withdraw_bids(claimed, at=now())
    auction.refresh_from_db()
    ai = _ai_team("AI Alpha", "AIA")
    _ai_roster(ai)

    placed, error = place_ai_bids(at=now())

    assert (placed, error) == (1, "")
    assert auction.current_price == auction.reserve_price
    assert auction.bids.live().get().bidder_team_id == ai.pk


def test_only_one_ai_team_bids_per_auction(db):
    seller = _seller()
    listed = _saved_rider("For Sale", seller, level=60)
    auction = list_for_auction(seller, listed.pk, at=now())
    first = _ai_team("AI Alpha", "AIA")
    _ai_roster(first)
    second = _ai_team("AI Beta", "AIB")
    _ai_roster(second)

    placed, error = place_ai_bids(at=now())

    assert (placed, error) == (1, "")
    # Both rosters are identical in shape, so buyer_rank's pk tiebreak decides.
    assert auction.bids.live().get().bidder_team_id == first.pk


def test_ai_skips_when_reserve_exceeds_headroom(db):
    seller = _seller()
    listed = _saved_rider("For Sale", seller, level=60)
    auction = list_for_auction(seller, listed.pk, at=now())
    # Half the reserve, so the cushion leaves it out of reach.
    poor = _ai_team("Poor AI", "POO", balance=auction.reserve_price // 2)
    _ai_roster(poor)

    placed, error = place_ai_bids(at=now())

    assert (placed, error) == (0, "")
    assert auction.bids.exists() is False


def test_ai_commitments_reduce_headroom_within_one_pass(db):
    seller = _seller()
    first_listed = _saved_rider("First", seller, level=40)
    second_listed = _saved_rider("Second", seller, level=40)
    first = list_for_auction(seller, first_listed.pk, at=now())
    second = list_for_auction(seller, second_listed.pk, at=now())
    # Equal reserves on purpose. The second listing is out of reach ONLY
    # because the first one already committed its reserve inside this pass, so
    # deleting `buyer.committed += auction.reserve_price` fails this test
    # rather than passing it by accident.
    assert first.reserve_price == second.reserve_price
    # Headroom of exactly one reserve: the first fits, the second does not.
    ai = _ai_team("AI Alpha", "AIA", balance=2 * first.reserve_price)
    _ai_roster(ai)

    placed, error = place_ai_bids(at=now())

    assert (placed, error) == (1, "")
    assert first.bids.live().count() == 1
    assert second.bids.exists() is False


def test_ai_commitments_reduce_headroom_across_ticks(db):
    seller = _seller()
    first_listed = _saved_rider("First", seller, level=40)
    first = list_for_auction(seller, first_listed.pk, at=now())
    # Headroom of exactly one reserve, and an equal reserve on the second
    # listing, so this pass can only afford it if the next one rebuilds the
    # commitment from the bid it is already holding.
    ai = _ai_team("AI Alpha", "AIA", balance=2 * first.reserve_price)
    _ai_roster(ai)

    placed, error = place_ai_bids(at=now())

    assert (placed, error) == (1, "")
    second_listed = _saved_rider("Second", seller, level=40)
    second = list_for_auction(seller, second_listed.pk, at=now())
    assert second.reserve_price == first.reserve_price

    later, error = place_ai_bids(at=now())

    assert (later, error) == (0, "")
    assert second.bids.exists() is False
    assert first.bids.live().count() == 1


def test_ai_never_raises_after_being_outbid(db):
    seller = _seller()
    listed = _saved_rider("For Sale", seller, level=60)
    auction = list_for_auction(seller, listed.pk, at=now())
    ai = _ai_team("AI Alpha", "AIA")
    _ai_roster(ai)
    place_ai_bids(at=now())
    human = _seller("HUM")
    place_bid(auction.pk, human, auction.current_price + auction.min_increment, at=now())
    auction.refresh_from_db()

    placed, error = place_ai_bids(at=now())

    assert (placed, error) == (0, "")
    assert auction.bids.live().count() == 2
    assert auction.current_price == auction.reserve_price + auction.min_increment


def test_ai_skips_auction_past_deadline(db):
    clock: MockClock = get_clock()
    seller = _seller()
    listed = _saved_rider("For Sale", seller, level=60)
    auction = list_for_auction(seller, listed.pk, at=now())
    ai = _ai_team("AI Alpha", "AIA")
    _ai_roster(ai)
    clock.set(auction.deadline + timedelta(hours=1))

    placed, error = place_ai_bids(at=now())

    assert (placed, error) == (0, "")
    assert auction.bids.exists() is False
    assert Auction.objects.get(pk=auction.pk).status == Auction.Status.OPEN


def _season() -> Season:
    return Season.objects.create(number=1, starts_at=now() - timedelta(weeks=8))


def _week(number: int, season: Season) -> Week:
    return Week.objects.create(
        season=season,
        number=number,
        starts_at=now(),
        ends_at=now() + timedelta(weeks=1),
    )


def _stagger_week(team: Team, season: Season) -> Week:
    """The week on which `team` is due to list: the stagger is
    `(week.number + team.pk) % AI_LISTING_EVERY_WEEKS`."""
    return _week(-team.pk % AI_LISTING_EVERY_WEEKS or AI_LISTING_EVERY_WEEKS, season)


def _ageing_roster(team: Team) -> tuple[list[Rider], Rider]:
    """A full (not surplus) roster whose one ageing non-top rider is the
    rider an ageing listing should sell: two stronger rouleurs it wants to
    keep, one it does not."""
    keepers = [
        _saved_rider("Keeper One", team, level=70, age=40, speciality=Rider.Speciality.ROULEUR),
        _saved_rider("Keeper Two", team, level=65, age=38, speciality=Rider.Speciality.ROULEUR),
    ]
    sellable = _saved_rider("Sellable", team, level=50, age=36, speciality=Rider.Speciality.ROULEUR)
    fillers = [
        _saved_rider(f"Filler {i}", team, level=40, speciality=Rider.Speciality.DOMESTIQUE)
        for i in range(9)
    ]
    return keepers + [sellable, *fillers], sellable


def test_ai_lists_surplus_rider_when_roster_above_normal(db):
    ai = _ai_team("AI Alpha", "AIA")
    _ai_roster(ai, size=12)
    surplus = _saved_rider("Surplus", ai, level=30, speciality=Rider.Speciality.DOMESTIQUE)

    listed, error = list_ai_riders(_stagger_week(ai, _season()), at=now())

    auction = Auction.objects.get()
    assert (listed, error) == (1, "")
    assert auction.rider_id == surplus.pk
    assert auction.seller_team_id == ai.pk
    assert auction.status == Auction.Status.OPEN


def test_ai_lists_ageing_rider_on_its_stagger_week_only(db):
    ai = _ai_team("AI Alpha", "AIA")
    _, sellable = _ageing_roster(ai)
    season = _season()
    on_week = _stagger_week(ai, season)
    off_week = _week(on_week.number + 1, season)

    skipped, error = list_ai_riders(off_week, at=now())

    assert (skipped, error) == (0, "")
    assert Auction.objects.exists() is False

    listed, error = list_ai_riders(on_week, at=now())

    assert (listed, error) == (1, "")
    assert Auction.objects.get().rider_id == sellable.pk


def test_ai_never_lists_below_min_roster(db):
    ai = _ai_team("AI Alpha", "AIA")
    _saved_rider("Keeper One", ai, level=70, age=40, speciality=Rider.Speciality.ROULEUR)
    _saved_rider("Keeper Two", ai, level=65, age=38, speciality=Rider.Speciality.ROULEUR)
    _saved_rider("Sellable", ai, level=50, age=36, speciality=Rider.Speciality.ROULEUR)
    for i in range(AI_MIN_ROSTER - 3):
        _saved_rider(f"Filler {i}", ai, level=40, speciality=Rider.Speciality.DOMESTIQUE)
    assert ai.riders.count() == AI_MIN_ROSTER

    listed, error = list_ai_riders(_stagger_week(ai, _season()), at=now())

    assert (listed, error) == (0, "")
    assert Auction.objects.exists() is False


def test_ai_lists_at_most_one_open_auction_per_team(db):
    ai = _ai_team("AI Alpha", "AIA")
    _ai_roster(ai, size=12)
    _saved_rider("Surplus One", ai, level=30, speciality=Rider.Speciality.DOMESTIQUE)
    _saved_rider("Surplus Two", ai, level=32, speciality=Rider.Speciality.DOMESTIQUE)

    listed, error = list_ai_riders(_stagger_week(ai, _season()), at=now())

    assert (listed, error) == (1, "")
    assert Auction.objects.filter(seller_team=ai, status=Auction.Status.OPEN).count() == 1


def test_ai_skips_a_team_that_already_has_an_open_listing(db):
    ai = _ai_team("AI Alpha", "AIA")
    _ai_roster(ai, size=12)
    # Stronger than the spare below, so the surplus rule would pick the spare
    # and not the already-listed rider: the open listing is then the only
    # thing that can stop this team listing twice.
    listed_already = _saved_rider("Already Listed", ai, level=45, speciality=Rider.Speciality.DOMESTIQUE)
    spare = _saved_rider("Spare Surplus", ai, level=30, speciality=Rider.Speciality.DOMESTIQUE)
    list_for_auction(ai, listed_already.pk, at=now())

    listed, error = list_ai_riders(_stagger_week(ai, _season()), at=now())

    assert (listed, error) == (0, "")
    open_auctions = Auction.objects.filter(seller_team=ai, status=Auction.Status.OPEN)
    assert open_auctions.count() == 1
    assert open_auctions.get().rider_id == listed_already.pk
    assert Auction.objects.filter(rider=spare).exists() is False


def test_ai_does_not_relist_rider_unsold_within_cooldown(db):
    ai = _ai_team("AI Alpha", "AIA")
    _, sellable = _ageing_roster(ai)
    Auction.objects.create(
        rider=sellable,
        seller_team=ai,
        reserve_price=10_000,
        current_price=10_000,
        min_increment=1_000,
        deadline=now() - timedelta(days=3),
        listed_at=now() - timedelta(days=5),
        status=Auction.Status.UNSOLD,
        resolved_at=now() - timedelta(weeks=1),
    )

    week = _stagger_week(ai, _season())
    blocked, error = list_ai_riders(week, at=now())

    assert (blocked, error) == (0, "")
    assert Auction.objects.filter(status=Auction.Status.OPEN).exists() is False

    relisted, error = list_ai_riders(week, at=now() + timedelta(weeks=5))

    assert (relisted, error) == (1, "")
    assert Auction.objects.filter(status=Auction.Status.OPEN, rider=sellable).exists()


def test_ai_skips_zero_reserve_rider(db):
    ai = _ai_team("AI Alpha", "AIA")
    _saved_rider("Keeper One", ai, level=70, age=40, speciality=Rider.Speciality.ROULEUR)
    _saved_rider("Keeper Two", ai, level=65, age=38, speciality=Rider.Speciality.ROULEUR)
    worthless = _saved_rider("Worthless", ai, level=10, age=40, speciality=Rider.Speciality.ROULEUR)
    for i in range(9):
        _saved_rider(f"Filler {i}", ai, level=40, speciality=Rider.Speciality.DOMESTIQUE)
    assert reserve_price_for(worthless) == 0

    listed, error = list_ai_riders(_stagger_week(ai, _season()), at=now())

    assert (listed, error) == (0, "")
    assert Auction.objects.exists() is False


def test_managed_team_is_never_listed_for(db):
    managed = _seller()
    for i in range(12):
        _saved_rider(f"Rider {i}", managed, level=40, speciality=Rider.Speciality.DOMESTIQUE)
    _saved_rider("Surplus", managed, level=30, speciality=Rider.Speciality.DOMESTIQUE)

    listed, error = list_ai_riders(_stagger_week(managed, _season()), at=now())

    assert (listed, error) == (0, "")
    assert Auction.objects.exists() is False
