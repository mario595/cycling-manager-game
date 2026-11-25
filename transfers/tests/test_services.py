from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import Mock, call

import pytest

from riders.development_squad import close_squad
from riders.models import Departure, DevelopmentSquad, Rider
from riders.youth_triage import promote
from teams.models import Team
from transfers.models import Auction, Bid
from transfers.pricing import min_increment_for, reserve_price_for, severance_fee_for
from transfers.services import (
    AuctionAlreadyExists,
    AUCTION_DURATION,
    AuctionNotOpen,
    BidTooLow,
    EXTENSION_WINDOW,
    FORCED_SALE_ROSTER_FLOOR,
    InsufficientFunds,
    ROSTER_CAP,
    RiderNotAvailable,
    RiderNotOnRoster,
    RosterAtFloor,
    RosterFull,
    SelfBid,
    cancel_listings,
    cancel_open_auctions,
    cancel_unowned_listings,
    force_list_for_auction,
    free_agents,
    list_for_auction,
    place_bid,
    release_cost_for,
    release_rider,
    resolve_auction,
    sign_free_agent,
    withdraw_bids,
)


def _rider(**overrides) -> Rider:
    """A persisted Rider — membership tests exercise `.team`, which an
    in-memory rider cannot carry."""
    defaults = dict(
        name="Test Rider",
        speciality=Rider.Speciality.ROULEUR,
        age=27,
        climb=50, sprint=50, flat=50, resistance=50, positioning=50,
    )
    defaults.update(overrides)
    return Rider.objects.create(**defaults)


@pytest.fixture
def claimed_at():
    return datetime(2027, 3, 1, 0, 0, tzinfo=dt_timezone.utc)


def test_free_agents_returns_only_teamless_riders(db):
    team = Team.objects.create(name="Team Alpha", code="ALP")
    rostered = _rider(name="A Rostered", team=team)
    bob = _rider(name="Bob Free", team=None)
    alice = _rider(name="Alice Free", team=None)

    pool = list(free_agents())

    assert pool == [alice, bob]  # ordered by name
    assert rostered not in pool


def test_free_agents_excludes_retired_riders(db):
    retired = _rider(
        name="Retired Rider", team=None,
        retired_at=datetime(2027, 3, 1, tzinfo=dt_timezone.utc),
    )
    active = _rider(name="Active Rider", team=None)

    assert list(free_agents()) == [active]
    assert retired not in free_agents()


def test_free_agents_excludes_squad_riders(db):
    team = Team.objects.create(name="Team Alpha", code="ALP")
    squad = DevelopmentSquad.objects.create(
        team=team, level=1, opened_at=datetime(2027, 3, 1, tzinfo=dt_timezone.utc),
    )
    squad_rider = _rider(name="Youth One", team=None, development_squad=squad)
    active = _rider(name="Active Rider", team=None)

    assert list(free_agents()) == [active]
    assert squad_rider not in free_agents()


def test_sign_squad_rider_raises_not_available(db, claimed_at):
    team = Team.objects.create(name="Team Alpha", code="ALP", managed_since=claimed_at)
    other_team = Team.objects.create(name="Team Beta", code="BET")
    squad = DevelopmentSquad.objects.create(
        team=other_team, level=1, opened_at=claimed_at,
    )
    rider = _rider(name="Youth One", team=None, development_squad=squad)
    charge = Mock()

    with pytest.raises(RiderNotAvailable):
        sign_free_agent(team, rider.pk, at=claimed_at, charge=charge)

    rider.refresh_from_db()
    charge.assert_not_called()
    assert rider.team_id is None
    assert rider.development_squad_id == squad.pk


def test_released_graduate_is_signable(db, claimed_at):
    """A graduate released by a squad close is a normal free agent and can be
    signed; a rider still mid-development is deleted instead and never
    reaches the market (#34)."""
    team = Team.objects.create(name="Team Alpha", code="ALP", managed_since=claimed_at)
    other_team = Team.objects.create(name="Team Beta", code="BET")
    squad = DevelopmentSquad.objects.create(
        team=other_team, level=1, opened_at=claimed_at,
    )
    graduate = _rider(
        name="Graduate One", team=None, development_squad=squad,
        intake_at=claimed_at, graduated_at=claimed_at,
    )
    in_development = _rider(
        name="Youth One", team=None, development_squad=squad,
        intake_at=claimed_at,
    )

    close_squad(other_team, at=claimed_at)
    signed = sign_free_agent(team, graduate.pk, at=claimed_at, charge=Mock())

    assert signed.team_id == team.pk
    assert not Rider.objects.filter(pk=in_development.pk).exists()


def test_signing_a_retired_rider_raises_not_available(db, claimed_at):
    team = Team.objects.create(name="Team Alpha", code="ALP", managed_since=claimed_at)
    retired_at = datetime(2027, 3, 1, tzinfo=dt_timezone.utc)
    rider = _rider(name="Retired Rider", team=None, retired_at=retired_at)
    charge = Mock()

    with pytest.raises(RiderNotAvailable):
        sign_free_agent(team, rider.pk, at=claimed_at, charge=charge)

    rider.refresh_from_db()
    charge.assert_not_called()
    assert rider.team_id is None
    assert rider.retired_at == retired_at


def test_release_cost_is_zero_during_claim_cooldown(db, claimed_at):
    team = Team.objects.create(
        name="Team Alpha", code="ALP", managed_since=claimed_at,
    )
    rider = _rider(name="Claimed Rider", team=team, joined_team_at=claimed_at)

    # No in-season week has opened since the claim — the claim cooldown
    # holds, so the inherited roster releases for free (Design decision 2).
    assert release_cost_for(team, rider, weeks_opened=0) == 0


def test_release_cost_is_full_severance_after_cooldown_expires(db, claimed_at):
    team = Team.objects.create(
        name="Team Alpha", code="ALP", managed_since=claimed_at,
    )
    rider = _rider(name="Claimed Rider", team=team, joined_team_at=claimed_at)

    cost = release_cost_for(team, rider, weeks_opened=1)

    assert cost == severance_fee_for(rider)
    assert cost > 0


def test_release_cost_is_full_severance_for_a_signed_rider(db, claimed_at):
    team = Team.objects.create(
        name="Team Alpha", code="ALP", managed_since=claimed_at,
    )
    # Signed in two days after the claim: joined_team_at is a *different*
    # timestamp than managed_since, so even with weeks_opened=0 the
    # exemption must not apply (Design decision 2 — "assigned, not chosen").
    rider = _rider(
        name="Signed Rider", team=team,
        joined_team_at=claimed_at + timedelta(days=2),
    )

    assert release_cost_for(team, rider, weeks_opened=0) == severance_fee_for(rider)
    assert release_cost_for(team, rider, weeks_opened=0) > 0


def test_sign_free_agent_assigns_the_rider_and_stamps_joining(db, claimed_at):
    team = Team.objects.create(
        name="Team Alpha", code="ALP", managed_since=claimed_at,
    )
    free = _rider(name="Free Rider", team=None, unattached_since=claimed_at)

    signed = sign_free_agent(team, free.pk, at=claimed_at)

    signed.refresh_from_db()
    assert signed.team_id == team.pk
    assert signed.joined_team_at == claimed_at
    assert signed.unattached_since is None


def test_sign_free_agent_refuses_an_already_signed_rider(db, claimed_at):
    team = Team.objects.create(
        name="Team Alpha", code="ALP", managed_since=claimed_at,
    )
    taken = _rider(name="Taken Rider", team=team, joined_team_at=claimed_at)

    # The availability re-check happens UNDER the lock, proven sequentially
    # the same way staff/tests proves hire_trainer's: the row is mutated
    # before the call, so the post-lock check must refuse it.
    with pytest.raises(RiderNotAvailable):
        sign_free_agent(team, taken.pk, at=claimed_at)


def test_sign_free_agent_refuses_over_cap(db, claimed_at):
    team = Team.objects.create(
        name="Team Alpha", code="ALP", managed_since=claimed_at,
    )
    for i in range(ROSTER_CAP):
        _rider(name=f"Roster {i}", team=team)
    free = _rider(name="Free Rider", team=None)

    with pytest.raises(RosterFull):
        sign_free_agent(team, free.pk, at=claimed_at)

    free.refresh_from_db()
    assert free.team_id is None
    assert free.unattached_since is None


def test_sign_free_agent_raises_from_charge_and_rolls_back(db, claimed_at):
    # Load-bearing: the one place a bug would silently create a free rider
    # or a money-losing one. A raised InsufficientFunds inside the
    # transaction must leave team and stamp untouched.
    team = Team.objects.create(
        name="Team Alpha", code="ALP", managed_since=claimed_at,
    )
    free = _rider(name="Free Rider", team=None)

    def charge(rider, fee):
        raise InsufficientFunds("You cannot afford this rider's signing fee.")

    with pytest.raises(InsufficientFunds):
        sign_free_agent(team, free.pk, at=claimed_at, charge=charge)

    free.refresh_from_db()
    assert free.team_id is None
    assert free.joined_team_at is None
    assert free.unattached_since is None


def test_release_rider_sends_the_rider_to_the_pool_and_stamps_leaving(db, claimed_at):
    team = Team.objects.create(
        name="Team Alpha", code="ALP", managed_since=claimed_at,
    )
    rider = _rider(name="Mine", team=team, joined_team_at=claimed_at)

    released = release_rider(team, rider.pk, at=claimed_at, weeks_opened=1)

    released.refresh_from_db()
    assert released.team_id is None
    assert released.unattached_since == claimed_at
    assert released.joined_team_at == claimed_at  # untouched by a release


def test_release_rider_refuses_a_rider_not_on_the_team(db, claimed_at):
    team_a = Team.objects.create(
        name="Team Alpha", code="ALP", managed_since=claimed_at,
    )
    team_b = Team.objects.create(name="Team Bravo", code="BRA")
    rider = _rider(name="Not Yours", team=team_a, joined_team_at=claimed_at)

    with pytest.raises(RiderNotOnRoster):
        release_rider(team_b, rider.pk, at=claimed_at, weeks_opened=0)


def test_list_for_auction_freezes_reserve_and_increment(db, claimed_at):
    team = Team.objects.create(name="Team Alpha", code="ALP")
    rider = _rider(name="For Sale", team=team)
    expected_reserve = reserve_price_for(rider)
    expected_increment = min_increment_for(expected_reserve)

    auction = list_for_auction(team, rider.pk, at=claimed_at)

    assert auction.rider_id == rider.pk
    assert auction.seller_team_id == team.pk
    assert auction.status == Auction.Status.OPEN
    assert auction.reserve_price == expected_reserve
    assert auction.current_price == expected_reserve
    assert auction.min_increment == expected_increment
    assert auction.listed_at == claimed_at
    assert auction.deadline > claimed_at

    # Mutating the rider afterwards must not move the frozen figures.
    rider.climb = 99
    rider.save(update_fields=["climb"])
    auction.refresh_from_db()
    assert auction.reserve_price == expected_reserve


def test_list_for_auction_rejects_rider_not_on_team(db, claimed_at):
    team_a = Team.objects.create(name="Team Alpha", code="ALP")
    team_b = Team.objects.create(name="Team Bravo", code="BRA")
    rider = _rider(name="Not Yours", team=team_a)

    with pytest.raises(RiderNotOnRoster):
        list_for_auction(team_b, rider.pk, at=claimed_at)

    assert Auction.objects.filter(rider=rider).count() == 0


def test_list_for_auction_rejects_second_concurrent_listing(db, claimed_at):
    team = Team.objects.create(name="Team Alpha", code="ALP")
    rider = _rider(name="For Sale", team=team)
    list_for_auction(team, rider.pk, at=claimed_at)

    with pytest.raises(AuctionAlreadyExists):
        list_for_auction(team, rider.pk, at=claimed_at)

    assert Auction.objects.filter(rider=rider, status=Auction.Status.OPEN).count() == 1


def test_place_bid_records_bid_and_updates_current_price(db, claimed_at):
    seller = Team.objects.create(name="Team Alpha", code="ALP")
    bidder = Team.objects.create(name="Team Bravo", code="BRA")
    rider = _rider(name="For Sale", team=seller)
    auction = list_for_auction(seller, rider.pk, at=claimed_at)
    bid_amount = auction.reserve_price

    updated = place_bid(auction.pk, bidder, bid_amount, at=claimed_at)

    assert updated.current_price == bid_amount
    assert Bid.objects.filter(auction=auction, bidder_team=bidder, amount=bid_amount).count() == 1


def test_place_bid_below_reserve_plus_increment_raises_bid_too_low(db, claimed_at):
    seller = Team.objects.create(name="Team Alpha", code="ALP")
    bidder = Team.objects.create(name="Team Bravo", code="BRA")
    rider = _rider(name="For Sale", team=seller)
    auction = list_for_auction(seller, rider.pk, at=claimed_at)

    with pytest.raises(BidTooLow):
        place_bid(auction.pk, bidder, auction.reserve_price - 1, at=claimed_at)


def test_place_bid_rejects_self_bid(db, claimed_at):
    seller = Team.objects.create(name="Team Alpha", code="ALP")
    rider = _rider(name="For Sale", team=seller)
    auction = list_for_auction(seller, rider.pk, at=claimed_at)

    with pytest.raises(SelfBid):
        place_bid(auction.pk, seller, auction.reserve_price, at=claimed_at)


def test_place_bid_on_closed_auction_raises_auction_not_open(db, claimed_at):
    seller = Team.objects.create(name="Team Alpha", code="ALP")
    bidder = Team.objects.create(name="Team Bravo", code="BRA")
    rider = _rider(name="For Sale", team=seller)
    auction = list_for_auction(seller, rider.pk, at=claimed_at)
    auction.status = Auction.Status.SOLD
    auction.save(update_fields=["status"])

    with pytest.raises(AuctionNotOpen):
        place_bid(auction.pk, bidder, auction.reserve_price, at=claimed_at)


def test_place_bid_within_extension_window_pushes_deadline_forward_by_the_window(db, claimed_at):
    seller = Team.objects.create(name="Team Alpha", code="ALP")
    bidder = Team.objects.create(name="Team Bravo", code="BRA")
    rider = _rider(name="For Sale", team=seller)
    auction = list_for_auction(seller, rider.pk, at=claimed_at)
    original_deadline = auction.deadline
    bid_time = original_deadline - EXTENSION_WINDOW / 2

    updated = place_bid(auction.pk, bidder, auction.reserve_price, at=bid_time)

    assert updated.deadline == original_deadline + EXTENSION_WINDOW


def test_place_bid_outside_extension_window_does_not_move_deadline(db, claimed_at):
    seller = Team.objects.create(name="Team Alpha", code="ALP")
    bidder = Team.objects.create(name="Team Bravo", code="BRA")
    rider = _rider(name="For Sale", team=seller)
    auction = list_for_auction(seller, rider.pk, at=claimed_at)
    original_deadline = auction.deadline
    bid_time = original_deadline - EXTENSION_WINDOW - timedelta(hours=1)

    updated = place_bid(auction.pk, bidder, auction.reserve_price, at=bid_time)

    assert updated.deadline == original_deadline


def test_place_bid_after_the_deadline_extends_from_now_not_from_the_stale_deadline(db, claimed_at):
    # A late tick: the auction's deadline has already passed but nothing
    # has resolved it yet, so it is still OPEN and a bid can land. Extending
    # from the stale deadline (deadline + EXTENSION_WINDOW) could still be
    # in the past if the tick is later than EXTENSION_WINDOW — the exact
    # snipe the extension exists to prevent. It must extend from `at`.
    seller = Team.objects.create(name="Team Alpha", code="ALP")
    bidder = Team.objects.create(name="Team Bravo", code="BRA")
    rider = _rider(name="For Sale", team=seller)
    auction = list_for_auction(seller, rider.pk, at=claimed_at)
    original_deadline = auction.deadline
    bid_time = original_deadline + EXTENSION_WINDOW * 3

    updated = place_bid(auction.pk, bidder, auction.reserve_price, at=bid_time)

    assert updated.deadline == bid_time + EXTENSION_WINDOW
    assert updated.deadline > bid_time


def test_resolve_auction_with_no_bids_marks_unsold_and_touches_nothing(db, claimed_at):
    seller = Team.objects.create(name="Team Alpha", code="ALP")
    rider = _rider(name="For Sale", team=seller)
    auction = list_for_auction(seller, rider.pk, at=claimed_at)
    charge_buyer = Mock()
    pay_seller = Mock()

    resolved = resolve_auction(
        auction, at=auction.deadline, charge_buyer=charge_buyer, pay_seller=pay_seller,
    )

    assert resolved.status == Auction.Status.UNSOLD
    assert resolved.resolved_at == auction.deadline
    charge_buyer.assert_not_called()
    pay_seller.assert_not_called()
    rider.refresh_from_db()
    assert rider.team_id == seller.pk


def test_resolve_auction_with_winning_bid_moves_rider_and_calls_both_callbacks_in_order(db, claimed_at):
    seller = Team.objects.create(name="Team Alpha", code="ALP")
    bidder = Team.objects.create(name="Team Bravo", code="BRA")
    rider = _rider(name="For Sale", team=seller)
    auction = list_for_auction(seller, rider.pk, at=claimed_at)
    place_bid(auction.pk, bidder, auction.reserve_price, at=claimed_at)

    manager = Mock()

    resolved = resolve_auction(
        auction, at=auction.deadline,
        charge_buyer=manager.charge_buyer, pay_seller=manager.pay_seller,
    )

    assert resolved.status == Auction.Status.SOLD
    assert manager.mock_calls == [
        call.charge_buyer(bidder, auction.reserve_price),
        call.pay_seller(seller, auction.reserve_price),
    ]
    rider.refresh_from_db()
    assert rider.team_id == bidder.pk


def test_resolve_auction_cancels_when_rider_already_left_roster(db, claimed_at):
    seller = Team.objects.create(name="Team Alpha", code="ALP")
    bidder = Team.objects.create(name="Team Bravo", code="BRA")
    rider = _rider(name="For Sale", team=seller)
    auction = list_for_auction(seller, rider.pk, at=claimed_at)
    place_bid(auction.pk, bidder, auction.reserve_price, at=claimed_at)
    release_rider(seller, rider.pk, at=claimed_at, weeks_opened=1)
    charge_buyer = Mock()
    pay_seller = Mock()

    resolved = resolve_auction(
        auction, at=auction.deadline, charge_buyer=charge_buyer, pay_seller=pay_seller,
    )

    assert resolved.status == Auction.Status.CANCELLED
    charge_buyer.assert_not_called()
    pay_seller.assert_not_called()
    rider.refresh_from_db()
    assert rider.team_id is None


def test_resolve_auction_marks_unsold_when_winner_at_roster_cap(db, claimed_at):
    seller = Team.objects.create(name="Team Alpha", code="ALP")
    bidder = Team.objects.create(name="Team Bravo", code="BRA")
    rider = _rider(name="For Sale", team=seller)
    auction = list_for_auction(seller, rider.pk, at=claimed_at)
    place_bid(auction.pk, bidder, auction.reserve_price, at=claimed_at)
    for i in range(ROSTER_CAP):
        _rider(name=f"Roster {i}", team=bidder)
    charge_buyer = Mock()
    pay_seller = Mock()

    resolved = resolve_auction(
        auction, at=auction.deadline, charge_buyer=charge_buyer, pay_seller=pay_seller,
    )

    assert resolved.status == Auction.Status.UNSOLD
    charge_buyer.assert_not_called()
    pay_seller.assert_not_called()
    rider.refresh_from_db()
    assert rider.team_id == seller.pk


def test_resolve_auction_is_idempotent_under_charge_buyer_failure(db, claimed_at):
    seller = Team.objects.create(name="Team Alpha", code="ALP")
    bidder = Team.objects.create(name="Team Bravo", code="BRA")
    rider = _rider(name="For Sale", team=seller)
    auction = list_for_auction(seller, rider.pk, at=claimed_at)
    place_bid(auction.pk, bidder, auction.reserve_price, at=claimed_at)

    def charge_buyer(team, amount):
        raise InsufficientFunds("Balance changed since the bid was placed.")

    pay_seller = Mock()

    with pytest.raises(InsufficientFunds):
        resolve_auction(auction, at=auction.deadline, charge_buyer=charge_buyer, pay_seller=pay_seller)

    pay_seller.assert_not_called()
    auction.refresh_from_db()
    assert auction.status == Auction.Status.OPEN
    assert auction.resolved_at is None
    rider.refresh_from_db()
    assert rider.team_id == seller.pk
    assert Bid.objects.filter(auction=auction).count() == 1


def test_withdraw_bids_resets_current_price_to_next_live_bid(db, claimed_at):
    seller = Team.objects.create(name="Seller", code="SEL")
    first_bidder = Team.objects.create(name="First Bidder", code="FIR")
    second_bidder = Team.objects.create(name="Second Bidder", code="SEC")
    rider = _rider(name="For Sale", team=seller)
    auction = list_for_auction(seller, rider.pk, at=claimed_at)
    place_bid(auction.pk, first_bidder, auction.reserve_price, at=claimed_at)
    place_bid(
        auction.pk,
        second_bidder,
        auction.reserve_price + auction.min_increment,
        at=claimed_at + timedelta(minutes=1),
    )

    withdrawn = withdraw_bids(second_bidder, at=claimed_at + timedelta(minutes=2))

    auction.refresh_from_db()
    assert withdrawn == 1
    assert auction.current_price == auction.reserve_price
    assert list(auction.bids.live()) == [first_bidder.transfer_bids.get()]


def test_withdraw_bids_resets_to_reserve_when_no_bid_remains(db, claimed_at):
    seller = Team.objects.create(name="Seller", code="SEL")
    bidder = Team.objects.create(name="Bidder", code="BID")
    rider = _rider(name="For Sale", team=seller)
    auction = list_for_auction(seller, rider.pk, at=claimed_at)
    place_bid(auction.pk, bidder, auction.reserve_price, at=claimed_at)

    withdrawn = withdraw_bids(bidder, at=claimed_at + timedelta(minutes=1))

    auction.refresh_from_db()
    assert withdrawn == 1
    assert auction.current_price == auction.reserve_price
    assert not auction.bids.live().exists()


def test_withdraw_bids_ignores_resolved_auctions(db, claimed_at):
    seller = Team.objects.create(name="Seller", code="SEL")
    bidder = Team.objects.create(name="Bidder", code="BID")
    rider = _rider(name="For Sale", team=seller)
    auction = list_for_auction(seller, rider.pk, at=claimed_at)
    place_bid(auction.pk, bidder, auction.reserve_price, at=claimed_at)
    auction.status = Auction.Status.UNSOLD
    auction.resolved_at = claimed_at + timedelta(minutes=1)
    auction.save(update_fields=["status", "resolved_at", "updated_at"])

    withdrawn = withdraw_bids(bidder, at=claimed_at + timedelta(minutes=2))

    bid = bidder.transfer_bids.get(auction=auction)
    assert withdrawn == 0
    assert bid.withdrawn_at is None
    assert auction.bids.live().exists()


def test_withdraw_bids_leaves_other_teams_bids_live(db, claimed_at):
    seller = Team.objects.create(name="Seller", code="SEL")
    first_bidder = Team.objects.create(name="First Bidder", code="FIR")
    second_bidder = Team.objects.create(name="Second Bidder", code="SEC")
    rider = _rider(name="For Sale", team=seller)
    auction = list_for_auction(seller, rider.pk, at=claimed_at)
    place_bid(auction.pk, first_bidder, auction.reserve_price, at=claimed_at)
    place_bid(
        auction.pk,
        second_bidder,
        auction.reserve_price + auction.min_increment,
        at=claimed_at + timedelta(minutes=1),
    )

    withdraw_bids(first_bidder, at=claimed_at + timedelta(minutes=2))

    assert not first_bidder.transfer_bids.live().exists()
    assert second_bidder.transfer_bids.live().exists()


def test_withdrawn_bid_never_wins_resolution(db, claimed_at):
    seller = Team.objects.create(name="Seller", code="SEL")
    first_bidder = Team.objects.create(name="First Bidder", code="FIR")
    second_bidder = Team.objects.create(name="Second Bidder", code="SEC")
    rider = _rider(name="For Sale", team=seller)
    auction = list_for_auction(seller, rider.pk, at=claimed_at)
    place_bid(auction.pk, first_bidder, auction.reserve_price, at=claimed_at)
    place_bid(
        auction.pk,
        second_bidder,
        auction.reserve_price + auction.min_increment,
        at=claimed_at + timedelta(minutes=1),
    )
    withdraw_bids(second_bidder, at=claimed_at + timedelta(minutes=2))
    charge_buyer = Mock()
    pay_seller = Mock()

    resolved = resolve_auction(
        auction,
        at=auction.deadline,
        charge_buyer=charge_buyer,
        pay_seller=pay_seller,
    )

    assert resolved.status == Auction.Status.SOLD
    assert charge_buyer.call_args.args == (first_bidder, auction.reserve_price)
    pay_seller.assert_called_once_with(seller, auction.reserve_price)
    rider.refresh_from_db()
    assert rider.team_id == first_bidder.pk


def test_withdrawn_only_bid_resolves_unsold(db, claimed_at):
    seller = Team.objects.create(name="Seller", code="SEL")
    bidder = Team.objects.create(name="Bidder", code="BID")
    rider = _rider(name="For Sale", team=seller)
    auction = list_for_auction(seller, rider.pk, at=claimed_at)
    place_bid(auction.pk, bidder, auction.reserve_price, at=claimed_at)
    withdraw_bids(bidder, at=claimed_at + timedelta(minutes=1))
    charge_buyer = Mock()
    pay_seller = Mock()

    resolved = resolve_auction(
        auction,
        at=auction.deadline,
        charge_buyer=charge_buyer,
        pay_seller=pay_seller,
    )

    assert resolved.status == Auction.Status.UNSOLD
    charge_buyer.assert_not_called()
    pay_seller.assert_not_called()
    rider.refresh_from_db()
    assert rider.team_id == seller.pk


def test_opening_bid_after_withdrawal_accepts_reserve(db, claimed_at):
    seller = Team.objects.create(name="Seller", code="SEL")
    first_bidder = Team.objects.create(name="First Bidder", code="FIR")
    second_bidder = Team.objects.create(name="Second Bidder", code="SEC")
    rider = _rider(name="For Sale", team=seller)
    auction = list_for_auction(seller, rider.pk, at=claimed_at)
    place_bid(auction.pk, first_bidder, auction.reserve_price, at=claimed_at)
    withdraw_bids(first_bidder, at=claimed_at + timedelta(minutes=1))

    updated = place_bid(
        auction.pk,
        second_bidder,
        auction.reserve_price,
        at=claimed_at + timedelta(minutes=2),
    )

    assert updated.current_price == auction.reserve_price
    assert auction.bids.live().count() == 1
    assert auction.bids.live().get().bidder_team_id == second_bidder.pk


def test_cancel_open_auctions_cancels_only_open(db, claimed_at):
    seller = Team.objects.create(name="Seller", code="SEL")
    bidder = Team.objects.create(name="Bidder", code="BID")
    rider = _rider(name="For Sale", team=seller)
    open_auction = list_for_auction(seller, rider.pk, at=claimed_at)
    place_bid(open_auction.pk, bidder, open_auction.reserve_price, at=claimed_at)
    sold = list_for_auction(seller, _rider(name="Sold", team=seller).pk, at=claimed_at)
    sold.status = Auction.Status.SOLD
    sold.save(update_fields=["status", "updated_at"])
    unsold = list_for_auction(seller, _rider(name="Unsold", team=seller).pk, at=claimed_at)
    unsold.status = Auction.Status.UNSOLD
    unsold.save(update_fields=["status", "updated_at"])
    retired = datetime(2027, 3, 8, tzinfo=dt_timezone.utc)

    cancelled = cancel_open_auctions([rider.pk], at=retired)

    open_auction.refresh_from_db()
    sold.refresh_from_db()
    unsold.refresh_from_db()
    assert cancelled == 1
    assert open_auction.status == Auction.Status.CANCELLED
    assert open_auction.resolved_at == retired
    assert sold.status == Auction.Status.SOLD
    assert sold.resolved_at is None
    assert unsold.status == Auction.Status.UNSOLD
    assert unsold.resolved_at is None


def test_cancel_open_auctions_keeps_bid_history(db, claimed_at):
    """Bids are append-only, so cancelling an auction leaves the record of
    who was interested — which is also the structural proof that no money
    moved: the function has no charge or pay callback to move any."""
    seller = Team.objects.create(name="Seller", code="SEL")
    bidder = Team.objects.create(name="Bidder", code="BID")
    rider = _rider(name="For Sale", team=seller)
    auction = list_for_auction(seller, rider.pk, at=claimed_at)
    place_bid(auction.pk, bidder, auction.reserve_price, at=claimed_at)

    cancel_open_auctions([rider.pk], at=claimed_at + timedelta(minutes=1))

    assert auction.bids.count() == 1
    assert auction.bids.get().amount == auction.reserve_price
    assert auction.bids.get().bidder_team_id == bidder.pk


# --- Graduates on the market (#34) ------------------------------------------------
#
# A graduate has no team but still belongs to the squad that developed them,
# so they are the seller's to list; a rider mid-development is not, and
# selling them would let a squad be emptied for profit rather than by choice.


def _graduate(team, *, name="Graduate", at=None):
    """A rider who has served their spell in `team`'s development squad."""
    at = at or datetime(2027, 3, 1, tzinfo=dt_timezone.utc)
    squad = DevelopmentSquad.objects.create(team=team, level=1, opened_at=at)
    return _rider(
        name=name, team=None, development_squad=squad,
        intake_at=at, graduated_at=at,
    )


def test_list_for_auction_accepts_a_graduate(db, claimed_at):
    team = Team.objects.create(name="Team Alpha", code="ALP")
    graduate = _graduate(team, at=claimed_at)

    auction = list_for_auction(team, graduate.pk, at=claimed_at)

    assert auction.status == Auction.Status.OPEN
    assert auction.seller_team_id == team.pk


def test_list_for_auction_refuses_a_rider_still_in_the_squad(db, claimed_at):
    """The squad's own prospects are not for sale until they graduate."""
    team = Team.objects.create(name="Team Alpha", code="ALP")
    squad = DevelopmentSquad.objects.create(team=team, level=1, opened_at=claimed_at)
    prospect = _rider(
        name="Prospect", team=None, development_squad=squad, intake_at=claimed_at,
    )

    with pytest.raises(RiderNotOnRoster):
        list_for_auction(team, prospect.pk, at=claimed_at)

    assert Auction.objects.filter(rider=prospect).count() == 0


def test_list_for_auction_refuses_another_teams_graduate(db, claimed_at):
    """A rival's graduate is as untouchable as a rival's roster rider."""
    mine = Team.objects.create(name="Team Alpha", code="ALP")
    theirs = Team.objects.create(name="Team Bravo", code="BRA")
    theirs_graduate = _graduate(theirs, at=claimed_at)

    with pytest.raises(RiderNotOnRoster):
        list_for_auction(mine, theirs_graduate.pk, at=claimed_at)


def test_resolve_sold_graduate_moves_to_buyer_and_leaves_the_squad(db, claimed_at):
    seller = Team.objects.create(name="Team Alpha", code="ALP")
    bidder = Team.objects.create(name="Team Bravo", code="BRA")
    graduate = _graduate(seller, at=claimed_at)
    auction = list_for_auction(seller, graduate.pk, at=claimed_at)
    place_bid(auction.pk, bidder, auction.reserve_price, at=claimed_at)

    resolved = resolve_auction(auction, at=auction.deadline)

    assert resolved.status == Auction.Status.SOLD
    graduate.refresh_from_db()
    assert graduate.team_id == bidder.pk
    assert graduate.development_squad_id is None


def test_resolve_unsold_graduate_drops_them_into_the_pool(db, claimed_at):
    """An unsold listing must not strand a graduate: they leave the squad and
    join the free-agent market stamped, rather than sitting invisible on the
    squad screen with nothing left to do about them."""
    seller = Team.objects.create(name="Team Alpha", code="ALP")
    graduate = _graduate(seller, at=claimed_at)
    auction = list_for_auction(seller, graduate.pk, at=claimed_at)

    resolved = resolve_auction(auction, at=auction.deadline)

    assert resolved.status == Auction.Status.UNSOLD
    graduate.refresh_from_db()
    assert graduate.development_squad_id is None
    assert graduate.team_id is None
    assert graduate.unattached_since == auction.deadline


def test_resolve_released_graduate_to_a_full_buyer_also_drops_them_in_the_pool(
    db, claimed_at,
):
    """The other UNSOLD path releases a graduate too — the buyer's roster is
    full, so the sale falls through exactly as if nobody had bid."""
    seller = Team.objects.create(name="Team Alpha", code="ALP")
    bidder = Team.objects.create(name="Team Bravo", code="BRA")
    graduate = _graduate(seller, at=claimed_at)
    auction = list_for_auction(seller, graduate.pk, at=claimed_at)
    place_bid(auction.pk, bidder, auction.reserve_price, at=claimed_at)
    for i in range(ROSTER_CAP):
        _rider(name=f"Filler {i}", team=bidder)

    resolved = resolve_auction(auction, at=auction.deadline)

    assert resolved.status == Auction.Status.UNSOLD
    graduate.refresh_from_db()
    assert graduate.development_squad_id is None
    assert graduate.unattached_since == auction.deadline


def test_resolve_auction_still_sells_a_graduate_promoted_mid_auction(db, claimed_at):
    """`resolve_auction`'s own rule: promotion moves a graduate onto the
    roster, and `belongs_to` is true both before and after, so the service
    does not void the sale.

    The API never reaches this state — `PromoteSquadRiderView` cancels the
    listing in the same transaction as the promotion (api/README.md). This
    pins the service, so a promotion from any other path still resolves as a
    sale rather than being cancelled as a lost rider."""
    seller = Team.objects.create(name="Team Alpha", code="ALP")
    buyer = Team.objects.create(name="Team Bravo", code="BRA")
    graduate = _graduate(seller, at=claimed_at)
    auction = list_for_auction(seller, graduate.pk, at=claimed_at)
    place_bid(auction.pk, buyer, auction.reserve_price, at=claimed_at)
    promote(seller, graduate.pk, at=claimed_at, roster_cap=ROSTER_CAP)
    graduate.refresh_from_db()
    assert graduate.team_id == seller.pk
    assert graduate.development_squad_id is None

    resolved = resolve_auction(auction, at=auction.deadline)

    assert resolved.status == Auction.Status.SOLD
    graduate.refresh_from_db()
    assert graduate.team_id == buyer.pk


def test_cancel_unowned_listings_cancels_only_listings_the_team_has_lost(db, claimed_at):
    """Called after a squad close: a released graduate's auction and a
    departed roster rider's both go, while a listing the team still owns is
    left running (#34)."""
    team = Team.objects.create(name="Team Alpha", code="ALP")
    bidder = Team.objects.create(name="Team Bravo", code="BRA")
    graduate = _graduate(team, at=claimed_at)
    roster_rider = _rider(name="Roster", team=team)
    kept_rider = _rider(name="Kept", team=team)
    graduate_auction = list_for_auction(team, graduate.pk, at=claimed_at)
    roster_auction = list_for_auction(team, roster_rider.pk, at=claimed_at)
    kept_auction = list_for_auction(team, kept_rider.pk, at=claimed_at)
    for auction in (graduate_auction, roster_auction, kept_auction):
        place_bid(auction.pk, bidder, auction.reserve_price, at=claimed_at)
    # Both riders leave the team: the graduate by the squad close that
    # releases them, the roster rider by being released. Before either, the
    # graduate's listing is still the team's and must survive.
    assert cancel_unowned_listings(team, at=claimed_at) == 0
    close_squad(team, at=claimed_at)
    release_rider(team, roster_rider.pk, at=claimed_at, weeks_opened=1)

    cancelled = cancel_unowned_listings(team, at=claimed_at)

    assert cancelled == 2
    assert Auction.objects.get(pk=graduate_auction.pk).status == Auction.Status.CANCELLED
    assert Auction.objects.get(pk=roster_auction.pk).status == Auction.Status.CANCELLED
    assert Auction.objects.get(pk=kept_auction.pk).status == Auction.Status.OPEN


def test_cancel_unowned_listings_leaves_a_forced_sale_running(db, claimed_at):
    """A forced sale's rider is teamless by design (#27), so `belongs_to` is
    false for them — but the team is still owed the sale, and closing the
    squad must not cancel it."""
    team = Team.objects.create(name="Team Alpha", code="ALP")
    riders = [_rider(name=f"Roster {i}", team=team) for i in range(FORCED_SALE_ROSTER_FLOOR + 1)]
    forced = force_list_for_auction(team, riders[0].pk, at=claimed_at)

    assert cancel_unowned_listings(team, at=claimed_at) == 0
    forced.refresh_from_db()
    assert forced.status == Auction.Status.OPEN


def test_cancel_listings_cancels_the_teams_open_listings(db, claimed_at):
    seller = Team.objects.create(name="Seller", code="SEL")
    bidder = Team.objects.create(name="Bidder", code="BID")
    first = list_for_auction(seller, _rider(name="First", team=seller).pk, at=claimed_at)
    second = list_for_auction(seller, _rider(name="Second", team=seller).pk, at=claimed_at)
    place_bid(first.pk, bidder, first.reserve_price, at=claimed_at)
    claimed = claimed_at + timedelta(minutes=1)

    cancelled = cancel_listings(seller, at=claimed)

    first.refresh_from_db()
    second.refresh_from_db()
    assert cancelled == 2
    assert first.status == Auction.Status.CANCELLED
    assert first.resolved_at == claimed
    assert second.status == Auction.Status.CANCELLED
    assert second.resolved_at == claimed


def test_cancel_listings_leaves_other_sellers_and_closed_auctions_alone(db, claimed_at):
    seller = Team.objects.create(name="Seller", code="SEL")
    other = Team.objects.create(name="Other", code="OTH")
    other_listing = list_for_auction(other, _rider(name="Theirs", team=other).pk, at=claimed_at)
    sold = list_for_auction(seller, _rider(name="Sold", team=seller).pk, at=claimed_at)
    sold.status = Auction.Status.SOLD
    sold.resolved_at = claimed_at + timedelta(minutes=1)
    sold.save(update_fields=["status", "resolved_at", "updated_at"])
    unsold = list_for_auction(seller, _rider(name="Unsold", team=seller).pk, at=claimed_at)
    unsold.status = Auction.Status.UNSOLD
    unsold.resolved_at = claimed_at + timedelta(minutes=2)
    unsold.save(update_fields=["status", "resolved_at", "updated_at"])
    claimed = claimed_at + timedelta(minutes=3)

    cancelled = cancel_listings(seller, at=claimed)

    other_listing.refresh_from_db()
    sold.refresh_from_db()
    unsold.refresh_from_db()
    assert cancelled == 0
    assert other_listing.status == Auction.Status.OPEN
    assert other_listing.resolved_at is None
    assert sold.status == Auction.Status.SOLD
    assert sold.resolved_at == claimed_at + timedelta(minutes=1)
    assert unsold.status == Auction.Status.UNSOLD
    assert unsold.resolved_at == claimed_at + timedelta(minutes=2)


def test_cancel_listings_keeps_bids_live_as_history(db, claimed_at):
    """The bids were not withdrawn — the auction ended — so `withdrawn_at`
    stays null. Every reader that counts them filters on an OPEN auction."""
    seller = Team.objects.create(name="Seller", code="SEL")
    bidder = Team.objects.create(name="Bidder", code="BID")
    rider = _rider(name="For Sale", team=seller)
    auction = list_for_auction(seller, rider.pk, at=claimed_at)
    place_bid(auction.pk, bidder, auction.reserve_price, at=claimed_at)

    cancel_listings(seller, at=claimed_at + timedelta(minutes=1))

    bid = auction.bids.get()
    assert bid.amount == auction.reserve_price
    assert bid.bidder_team_id == bidder.pk
    assert bid.withdrawn_at is None


def test_cancel_listings_with_nothing_open_returns_zero(db, claimed_at):
    seller = Team.objects.create(name="Seller", code="SEL")
    rider = _rider(name="For Sale", team=seller)
    auction = list_for_auction(seller, rider.pk, at=claimed_at)

    assert cancel_listings(seller, at=claimed_at) == 1
    assert cancel_listings(seller, at=claimed_at + timedelta(minutes=1)) == 0
    auction.refresh_from_db()
    assert auction.status == Auction.Status.CANCELLED


# -- forced sales under insolvency (#27) -----------------------------------

def _roster(team, size: int) -> list[Rider]:
    return [_rider(name=f"Roster {team.code} {i}", team=team) for i in range(size)]


def test_force_list_moves_rider_off_roster_and_opens_forced_auction(db, claimed_at):
    seller = Team.objects.create(name="Team Alpha", code="ALP")
    riders = _roster(seller, 6)

    auction = force_list_for_auction(seller, riders[0].pk, at=claimed_at)

    riders[0].refresh_from_db()
    assert riders[0].team_id is None
    assert auction.forced is True
    assert auction.status == Auction.Status.OPEN
    assert auction.seller_team_id == seller.pk
    assert auction.reserve_price == reserve_price_for(riders[0])
    assert auction.deadline == claimed_at + AUCTION_DURATION


def test_force_list_charges_nothing(db, claimed_at):
    from economy.models import LedgerEntry

    seller = Team.objects.create(name="Team Alpha", code="ALP")
    riders = _roster(seller, 6)

    force_list_for_auction(seller, riders[0].pk, at=claimed_at)

    assert LedgerEntry.objects.filter(team=seller).count() == 0


def test_force_list_refused_at_roster_floor(db, claimed_at):
    seller = Team.objects.create(name="Team Alpha", code="ALP")
    riders = _roster(seller, FORCED_SALE_ROSTER_FLOOR)

    with pytest.raises(RosterAtFloor):
        force_list_for_auction(seller, riders[0].pk, at=claimed_at)

    riders[0].refresh_from_db()
    assert riders[0].team_id == seller.pk
    assert Auction.objects.count() == 0


def test_force_list_rejects_rider_not_on_team(db, claimed_at):
    seller = Team.objects.create(name="Team Alpha", code="ALP")
    other = Team.objects.create(name="Team Bravo", code="BRA")
    _roster(seller, 6)
    foreign = _rider(name="Foreign", team=other)

    with pytest.raises(RiderNotOnRoster):
        force_list_for_auction(seller, foreign.pk, at=claimed_at)


def test_force_list_converts_existing_voluntary_auction(db, claimed_at):
    seller = Team.objects.create(name="Team Alpha", code="ALP")
    bidder = Team.objects.create(name="Team Bravo", code="BRA")
    riders = _roster(seller, 6)
    voluntary = list_for_auction(seller, riders[0].pk, at=claimed_at)
    place_bid(voluntary.pk, bidder, voluntary.reserve_price, at=claimed_at)

    converted = force_list_for_auction(seller, riders[0].pk, at=claimed_at)

    assert converted.pk == voluntary.pk
    assert converted.forced is True
    assert converted.bids.live().count() == 1
    assert Auction.objects.count() == 1


def test_force_listed_rider_not_in_free_agent_pool(db, claimed_at):
    seller = Team.objects.create(name="Team Alpha", code="ALP")
    riders = _roster(seller, 6)

    force_list_for_auction(seller, riders[0].pk, at=claimed_at)

    assert riders[0] not in free_agents()


def test_force_listed_rider_cannot_be_signed(db, claimed_at):
    seller = Team.objects.create(name="Team Alpha", code="ALP")
    buyer = Team.objects.create(name="Team Bravo", code="BRA")
    riders = _roster(seller, 6)
    force_list_for_auction(seller, riders[0].pk, at=claimed_at)

    with pytest.raises(RiderNotAvailable):
        sign_free_agent(buyer, riders[0].pk, at=claimed_at)

    riders[0].refresh_from_db()
    assert riders[0].team_id is None


def test_resolve_forced_sold_pays_seller_and_moves_rider(db, claimed_at):
    seller = Team.objects.create(name="Team Alpha", code="ALP")
    bidder = Team.objects.create(name="Team Bravo", code="BRA")
    riders = _roster(seller, 6)
    auction = force_list_for_auction(seller, riders[0].pk, at=claimed_at)
    place_bid(auction.pk, bidder, auction.reserve_price, at=claimed_at)
    manager = Mock()

    resolved = resolve_auction(
        auction, at=auction.deadline,
        charge_buyer=manager.charge_buyer, pay_seller=manager.pay_seller,
    )

    assert resolved.status == Auction.Status.SOLD
    assert manager.mock_calls == [
        call.charge_buyer(bidder, auction.reserve_price),
        call.pay_seller(seller, auction.reserve_price),
    ]
    riders[0].refresh_from_db()
    assert riders[0].team_id == bidder.pk


def test_resolve_forced_unsold_leaves_free_agent(db, claimed_at):
    seller = Team.objects.create(name="Team Alpha", code="ALP")
    riders = _roster(seller, 6)
    auction = force_list_for_auction(seller, riders[0].pk, at=claimed_at)

    resolved = resolve_auction(auction, at=auction.deadline)

    assert resolved.status == Auction.Status.UNSOLD
    riders[0].refresh_from_db()
    assert riders[0].team_id is None
    assert riders[0] in free_agents()


def test_resolve_forced_winner_at_cap_goes_unsold(db, claimed_at):
    seller = Team.objects.create(name="Team Alpha", code="ALP")
    bidder = Team.objects.create(name="Team Bravo", code="BRA")
    riders = _roster(seller, 6)
    auction = force_list_for_auction(seller, riders[0].pk, at=claimed_at)
    place_bid(auction.pk, bidder, auction.reserve_price, at=claimed_at)
    _roster(bidder, ROSTER_CAP)
    charge_buyer = Mock()

    resolved = resolve_auction(auction, at=auction.deadline, charge_buyer=charge_buyer)

    assert resolved.status == Auction.Status.UNSOLD
    charge_buyer.assert_not_called()
    riders[0].refresh_from_db()
    assert riders[0].team_id is None


def test_resolve_forced_cancels_when_rider_retired(db, claimed_at):
    seller = Team.objects.create(name="Team Alpha", code="ALP")
    riders = _roster(seller, 6)
    auction = force_list_for_auction(seller, riders[0].pk, at=claimed_at)
    riders[0].refresh_from_db()
    riders[0].retired_at = claimed_at
    riders[0].save()

    resolved = resolve_auction(auction, at=auction.deadline)

    assert resolved.status == Auction.Status.CANCELLED


def test_forced_sale_floor_matches_racing_squad_size():
    from racing.models import SQUAD_SIZE

    assert FORCED_SALE_ROSTER_FLOOR == SQUAD_SIZE


# --- Departures (#158, #162) ----------------------------------------------
# A sale and an unsold graduate's release happen while the seller is away, so
# both leave a departure behind; an unsold roster rider has not left at all.


def test_a_sale_records_a_departure_with_buyer_and_fee(db, claimed_at):
    seller = Team.objects.create(name="Team Alpha", code="ALP")
    bidder = Team.objects.create(name="Team Bravo", code="BRA")
    rider = _rider(name="For Sale", team=seller)
    auction = list_for_auction(seller, rider.pk, at=claimed_at)
    place_bid(auction.pk, bidder, auction.reserve_price, at=claimed_at)

    resolve_auction(auction, at=auction.deadline)

    departure = Departure.objects.get()
    assert departure.team == seller
    assert departure.kind == Departure.Kind.SOLD
    assert departure.buyer == bidder
    assert departure.fee == auction.reserve_price
    assert departure.at == auction.deadline


def test_a_forced_sale_records_against_the_seller(db, claimed_at):
    """The rider left the roster at listing (#27), so the seller is the
    auction's, not the rider's team."""
    seller = Team.objects.create(name="Team Alpha", code="ALP")
    bidder = Team.objects.create(name="Team Bravo", code="BRA")
    riders = _roster(seller, 6)
    auction = force_list_for_auction(seller, riders[0].pk, at=claimed_at)
    place_bid(auction.pk, bidder, auction.reserve_price, at=claimed_at)

    resolve_auction(auction, at=auction.deadline)

    departure = Departure.objects.get()
    assert (departure.team, departure.buyer, departure.kind) == (
        seller, bidder, Departure.Kind.SOLD,
    )


def test_an_unsold_graduate_is_recorded_as_released(db, claimed_at):
    seller = Team.objects.create(name="Team Alpha", code="ALP")
    graduate = _graduate(seller, at=claimed_at)
    auction = list_for_auction(seller, graduate.pk, at=claimed_at)

    resolve_auction(auction, at=auction.deadline)

    departure = Departure.objects.get()
    assert (departure.team, departure.rider, departure.kind) == (
        seller, graduate, Departure.Kind.RELEASED,
    )


def test_an_unsold_roster_rider_records_nothing(db, claimed_at):
    seller = Team.objects.create(name="Team Alpha", code="ALP")
    rider = _rider(name="For Sale", team=seller)
    auction = list_for_auction(seller, rider.pk, at=claimed_at)

    resolve_auction(auction, at=auction.deadline)

    assert not Departure.objects.exists()


def test_a_sale_that_rolls_back_records_nothing(db, claimed_at):
    seller = Team.objects.create(name="Team Alpha", code="ALP")
    bidder = Team.objects.create(name="Team Bravo", code="BRA")
    rider = _rider(name="For Sale", team=seller)
    auction = list_for_auction(seller, rider.pk, at=claimed_at)
    place_bid(auction.pk, bidder, auction.reserve_price, at=claimed_at)

    def pay_seller(team, amount):
        raise RuntimeError("ledger down")

    with pytest.raises(RuntimeError):
        resolve_auction(auction, at=auction.deadline, pay_seller=pay_seller)

    assert not Departure.objects.exists()
