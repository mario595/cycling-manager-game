from __future__ import annotations

from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import Mock, call

import pytest

from riders.models import Rider
from teams.models import Team
from transfers.models import Auction, Bid
from transfers.pricing import min_increment_for, reserve_price_for, severance_fee_for
from transfers.services import (
    AuctionAlreadyExists,
    AuctionNotOpen,
    BidTooLow,
    EXTENSION_WINDOW,
    InsufficientFunds,
    ROSTER_CAP,
    RiderNotAvailable,
    RiderNotOnRoster,
    RosterFull,
    SelfBid,
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
