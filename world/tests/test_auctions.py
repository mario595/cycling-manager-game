from __future__ import annotations

from datetime import timedelta

from economy.models import LedgerEntry
from riders.models import Rider
from teams.models import Team
from transfers.models import Auction
from transfers.services import EXTENSION_WINDOW, list_for_auction, place_bid
from world.clocks import MockClock
from world.services import get_clock, now, tick


def _team(name, code) -> Team:
    return Team.objects.create(name=name, code=code)


def _rider(name, team) -> Rider:
    return Rider.objects.create(
        name=name, team=team,
        climb=60, sprint=60, flat=60, resistance=60, positioning=60,
    )


def test_tick_resolves_an_expired_auction_even_with_no_week_transition(db):
    # No season is declared at all, so process_week_transitions returns
    # nothing and weeks_processed stays 0 — the concrete check that
    # resolution is wired outside `for transition in weeks:` (plan's
    # Design decision 2), which would otherwise leave this auction open
    # forever.
    clock: MockClock = get_clock()
    seller = _team("Seller", "SEL")
    bidder = _team("Bidder", "BID")
    rider = _rider("For Sale", seller)
    auction = list_for_auction(seller, rider.pk, at=now())
    place_bid(auction.pk, bidder, auction.reserve_price, at=now())

    clock.set(auction.deadline + timedelta(hours=1))
    run = tick()

    assert run.weeks_processed == 0
    assert run.auctions_sold == 1
    assert run.auctions_unsold == 0
    auction.refresh_from_db()
    assert auction.status == Auction.Status.SOLD
    rider.refresh_from_db()
    assert rider.team_id == bidder.pk
    assert LedgerEntry.objects.filter(
        team=bidder, kind=LedgerEntry.Kind.TRANSFER_FEE, amount=-auction.reserve_price,
    ).exists()
    assert LedgerEntry.objects.filter(
        team=seller, kind=LedgerEntry.Kind.TRANSFER_FEE, amount=auction.reserve_price,
    ).exists()


def test_tick_does_not_resolve_an_auction_before_its_deadline(db):
    clock: MockClock = get_clock()
    seller = _team("Seller", "SEL")
    bidder = _team("Bidder", "BID")
    rider = _rider("For Sale", seller)
    auction = list_for_auction(seller, rider.pk, at=now())
    place_bid(auction.pk, bidder, auction.reserve_price, at=now())

    clock.set(auction.deadline - timedelta(hours=1))
    run = tick()

    assert run.auctions_sold == 0
    assert run.auctions_unsold == 0
    auction.refresh_from_db()
    assert auction.status == Auction.Status.OPEN
    rider.refresh_from_db()
    assert rider.team_id == seller.pk


def test_tick_extends_deadline_test_still_resolves_eventually(db):
    # A bid landing near the deadline extends it (Design decision 2); the
    # auction must keep surviving ticks that land inside the extended
    # window and only resolve once bidding actually stops.
    clock: MockClock = get_clock()
    seller = _team("Seller", "SEL")
    bidder = _team("Bidder", "BID")
    rider = _rider("For Sale", seller)
    auction = list_for_auction(seller, rider.pk, at=now())

    bid_time = auction.deadline - EXTENSION_WINDOW / 2
    place_bid(auction.pk, bidder, auction.reserve_price, at=bid_time)
    auction.refresh_from_db()
    extended_deadline = auction.deadline
    assert extended_deadline > bid_time  # sanity: the bid did extend it

    # A tick landing at the ORIGINAL deadline must not resolve the
    # auction — its real deadline has moved forward.
    clock.set(bid_time)
    run = tick()
    assert run.auctions_sold == 0
    assert run.auctions_unsold == 0
    auction.refresh_from_db()
    assert auction.status == Auction.Status.OPEN

    # Once the EXTENDED deadline passes with no further bids, the next
    # tick resolves it.
    clock.set(extended_deadline + timedelta(hours=1))
    run = tick()
    assert run.auctions_sold == 1
    auction.refresh_from_db()
    assert auction.status == Auction.Status.SOLD
